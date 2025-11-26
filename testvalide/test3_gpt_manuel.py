import os
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
import pandas as pd
import time
from mistralai import Mistral
from PyPDF2 import PdfReader, PdfWriter
import tempfile
from dotenv import load_dotenv
import re
import requests
from openai import OpenAI



# --- Chargement des variables d’environnement ---
load_dotenv()
client = Mistral(api_key=os.getenv("MISTRAL_KEY"))
client_gpt = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# 🔹 Agents différents selon le mode choisi
AGENT_ID_RECTO_VERSO = os.getenv("MISTRAL_AGENT_RECTO_VERSO")
AGENT_ID_COMBINE = os.getenv("MISTRAL_AGENT_RECTO_VERSO")


ANKI_CONNECT_URL = "http://localhost:8765"


# --- Vérifier la connexion à AnkiConnect ---
def test_anki_connection():
    try:
        res = requests.post(ANKI_CONNECT_URL, json={"action": "version", "version": 6})
        if res.status_code == 200 and "result" in res.json():
            return True
    except Exception:
        pass
    return False


# --- Envoyer un fichier Excel vers Anki ---
def send_to_anki(excel_path, deck_name="RectoVerso", model_name="Basic", field_front="Recto", field_back="Verso"):
    if not os.path.exists(excel_path):
        messagebox.showerror("Erreur", f"Le fichier {excel_path} n’existe pas.")
        return

    if not test_anki_connection():
        messagebox.showerror(
            "Erreur",
            "AnkiConnect ne répond pas.\nAssure-toi qu’Anki est ouvert et que le module AnkiConnect est installé."
        )
        return

    df = pd.read_excel(excel_path)
    added = 0

    for _, row in df.iterrows():
        recto = str(row.get(field_front, "")).strip()
        verso = str(row.get(field_back, "")).strip()
        if not recto or not verso:
            continue

        payload = {
            "action": "addNote",
            "version": 6,
            "params": {
                "note": {
                    "deckName": deck_name,
                    "modelName": model_name,
                    "fields": {field_front: recto, field_back: verso},
                    "tags": ["auto_import"]
                }
            }
        }

        res = requests.post(ANKI_CONNECT_URL, json=payload).json()
        if res.get("error") is None:
            added += 1

    messagebox.showinfo("Anki", f"✅ {added} cartes ajoutées au deck '{deck_name}' avec succès !")


# --- UTILITAIRE EXCEL : append sécurisé ---
def safe_append_to_excel(new_data, output_excel):
    df_new = pd.DataFrame(new_data, columns=["Recto", "Verso"])
    if os.path.exists(output_excel):
        try:
            df_existing = pd.read_excel(output_excel)
            df_combined = pd.concat([df_existing, df_new], ignore_index=True)
        except Exception:
            df_combined = df_new
    else:
        df_combined = df_new

    df_combined.drop_duplicates(subset=["Recto", "Verso"], inplace=True)
    df_combined.to_excel(output_excel, index=False)


# --- OCR par lots ---
def process_pdf_with_mistral(pdf_path, agent_id, pages_per_batch=10):
    reader = PdfReader(pdf_path)
    total_pages = len(reader.pages)
    all_text = []
    for start in range(0, total_pages, pages_per_batch):
        end = min(start + pages_per_batch, total_pages)
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as temp_pdf:
            pdf_writer = PdfWriter()
            for i in range(start, end):
                pdf_writer.add_page(reader.pages[i])
            pdf_writer.write(temp_pdf)
            temp_path = temp_pdf.name

        with open(temp_path, "rb") as f:
            upload_res = client.files.upload(
                file={"file_name": f"chunk_{start+1}_to_{end}.pdf", "content": f},
                purpose="ocr"
            )
        file_id = upload_res.id
        signed = client.files.get_signed_url(file_id=file_id)
        document_url = signed.url

        ocr_res = client.ocr.process(
            model="mistral-ocr-latest",
            document={"type": "document_url", "document_url": document_url},
            include_image_base64=False
        )

        pages = getattr(ocr_res, "pages", None) or getattr(ocr_res, "output", None)
        if not pages:
            continue
        for page in pages:
            if hasattr(page, "markdown"):
                all_text.append(page.markdown)
            elif isinstance(page, str):
                all_text.append(page)
        os.remove(temp_path)
    return "\n".join(all_text)


# =======================================================
# 🔹 NOUVELLES FONCTIONS DE CLEANING ET VÉRIFICATION
# =======================================================

def nettoyer_texte_brut(texte):
    """Nettoie le texte OCR : supprime les titres, espaces, caractères inutiles."""
    texte = re.sub(r'\b(Thème|Corrigé|Exercice|Partie|VOCABULAIRE|Chapitre)\b.*', '', texte, flags=re.IGNORECASE)
    texte = re.sub(r'#{1,}|={2,}|-{2,}', '', texte)
    texte = re.sub(r'\s{2,}', ' ', texte)
    lignes = [l.strip() for l in texte.split('\n') if l.strip()]
    return lignes




def apparier_phrases(recto_lines, verso_lines, mistral_client=None,):
    """Essaie d’apparier les phrases  + vérifie la traduction si demandé."""
    numero_regex = re.compile(r'^\s*(?<!\d)(\d{1,2})(?!\d)[\.\)]?\s+')
    data = []
    i = j = 0
    while i < len(recto_lines) and j < len(verso_lines):
        L1 = recto_lines[i]
        L2 = verso_lines[j]

        num_recto = numero_regex.match(L1)
        num_verso = numero_regex.match(L2)

        # Gestion de l'ordre
        if num_recto and num_verso and num_recto.group(1) != num_verso.group(1):
            if int(num_recto.group(1)) < int(num_verso.group(1)):
                i += 1
                continue
            else:
                j += 1
                continue

        i += 1
        j += 1

    return data

def apparier_par_chatgpt(lignes):
    """
    Envoie les lignes OCR à ChatGPT et récupère des paires Recto/Verso
    au format texte simple.
    """

    prompt = f"""
    Voici du texte OCR :

    {lignes}

    ➤ Objectif :
      - Extrais uniquement les paires de vocabulaire.
      - Formate STRICTEMENT la réponse ainsi :

        Recto : mot ou phrase
        Verso : traduction

        (puis répète autant de fois que nécessaire)

    ⚠️ Aucun JSON, aucun commentaire.
    """

    try:
        response = client_gpt.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1,
        )

        text = response.choices[0].message.content.strip()
        lignes = text.split("\n")

        data = []
        recto = verso = None

        for line in lignes:
            if line.lower().startswith("recto"):
                recto = line.split(":", 1)[1].strip()
            elif line.lower().startswith("verso"):
                verso = line.split(":", 1)[1].strip()

            # Quand on a un couple complet
            if recto and verso:
                data.append({"Recto": recto, "Verso": verso})
                recto = verso = None

        return data

    except Exception as e:
        print("❌ Erreur ChatGPT :", e)
        return []




# =======================================================
# 🔹 MODES DE TRAITEMENT
# =======================================================

def imperator(pdf_verso, pdf_recto, output_excel, progress_callback=None, verifier=False):
    """Mode Recto/Verso avec nettoyage et appariement automatique"""
    start_time = time.time()

    recto_res = process_pdf_with_mistral(pdf_recto, AGENT_ID_RECTO_VERSO)
    verso_res = process_pdf_with_mistral(pdf_verso, AGENT_ID_RECTO_VERSO)

    recto_lines = nettoyer_texte_brut(recto_res)
    verso_lines = nettoyer_texte_brut(verso_res)

    data = apparier_phrases(recto_lines, verso_lines, mistral_client=client)

    safe_append_to_excel(data, output_excel)
    elapsed = round(time.time() - start_time, 2)
    progress_callback(100, f"Terminé ✅ ({elapsed}s)")
    return output_excel

def imperator_combine(pdf_combine, output_excel, progress_callback=None, ):
    start_time = time.time()

    # OCR
    res = process_pdf_with_mistral(pdf_combine, AGENT_ID_COMBINE)

    # Nettoyage
    lignes = nettoyer_texte_brut(res)

    # Appariement intelligent
    data = apparier_par_chatgpt(lignes)

    

    # Sauvegarde Excel
    safe_append_to_excel(data, output_excel)

    elapsed = round(time.time() - start_time, 2)
    progress_callback(100, f"Terminé ✅ ({elapsed}s)")
    return output_excel






# =======================================================
# 🔹 INTERFACE GRAPHIQUE
# =======================================================

class MistralApp:
    def __init__(self, root):
        self.root = root
        self.root.title("📘 OCR Mistral - Multi Mode + Anki")
        self.root.geometry("600x760")
        self.root.resizable(False, False)

        # --- Variables ---
        self.mode = tk.StringVar(value="recto_verso")
        self.pdf_recto = tk.StringVar()
        self.pdf_verso = tk.StringVar()
        self.pdf_unique = tk.StringVar()
        self.output_excel = tk.StringVar(value="resultats_traitement.xlsx")
        self.output_excel_anki = tk.StringVar(value="cartes_anki.xlsx")
        self.verifier_traductions = tk.BooleanVar(value=False)

        self.deck_name = tk.StringVar(value="RectoVerso")
        self.model_name = tk.StringVar(value="Basic")
        self.field_front = tk.StringVar(value="Recto")
        self.field_back = tk.StringVar(value="Verso")

        # --- Choix du mode ---
        ttk.Label(root, text="🧩 Sélection du mode :").pack(pady=(10, 5))
        frm_mode = ttk.Frame(root)
        frm_mode.pack()
        for mode, text in [
            ("recto_verso", "Recto/Verso"),
            ("combine", "Fichier combiné")
        ]:
            ttk.Radiobutton(frm_mode, text=text, variable=self.mode, value=mode, command=self.update_file_inputs).pack(side="left", padx=10)

        # --- Zone dynamique ---
        self.frm_files = ttk.Frame(root)
        self.frm_files.pack(pady=10)
        self.update_file_inputs()

        

        # --- Bouton traitement ---
        ttk.Button(root, text="▶ Lancer le traitement", command=self.run_processing).pack(pady=10)

        # --- Progression ---
        self.progress = ttk.Progressbar(root, length=350, mode="determinate")
        self.progress.pack(pady=(5, 5))
        self.status_label = ttk.Label(root, text="En attente...")
        self.status_label.pack()

        # --- Paramètres Anki ---
        ttk.Separator(root).pack(fill="x", pady=15)
        ttk.Label(root, text="⚙️ Paramètres Anki").pack()

        ttk.Label(root, text="Nom du fichier Excel (Anki) :").pack(pady=(8, 5))
        ttk.Entry(root, textvariable=self.output_excel_anki, width=55).pack()

        frm_anki = ttk.Frame(root)
        frm_anki.pack(pady=5)

        ttk.Label(frm_anki, text="Deck name :").grid(row=0, column=0, sticky="e", padx=5)
        ttk.Entry(frm_anki, textvariable=self.deck_name, width=25).grid(row=0, column=1)

        ttk.Label(frm_anki, text="Model name :").grid(row=1, column=0, sticky="e", padx=5)
        ttk.Entry(frm_anki, textvariable=self.model_name, width=25).grid(row=1, column=1)

        ttk.Label(frm_anki, text="Champ Recto :").grid(row=2, column=0, sticky="e", padx=5)
        ttk.Entry(frm_anki, textvariable=self.field_front, width=25).grid(row=2, column=1)

        ttk.Label(frm_anki, text="Champ Verso :").grid(row=3, column=0, sticky="e", padx=5)
        ttk.Entry(frm_anki, textvariable=self.field_back, width=25).grid(row=3, column=1)

        ttk.Button(root, text="📥 Envoyer vers Anki", command=self.send_to_anki).pack(pady=10)

    # --- Mise à jour dynamique de l'interface selon le mode ---
    def update_file_inputs(self):
        for widget in self.frm_files.winfo_children():
            widget.destroy()

        mode = self.mode.get()
        if mode == "recto_verso":
            ttk.Label(self.frm_files, text="📄 Sélection du PDF RECTO :").pack()
            ttk.Entry(self.frm_files, textvariable=self.pdf_recto, width=55).pack()
            ttk.Button(self.frm_files, text="Parcourir", command=self.select_recto).pack(pady=3)

            ttk.Label(self.frm_files, text="📄 Sélection du PDF VERSO :").pack(pady=(10, 0))
            ttk.Entry(self.frm_files, textvariable=self.pdf_verso, width=55).pack()
            ttk.Button(self.frm_files, text="Parcourir", command=self.select_verso).pack(pady=3)

        else:
            ttk.Label(self.frm_files, text="📄 Sélection du PDF :").pack()
            ttk.Entry(self.frm_files, textvariable=self.pdf_unique, width=55).pack()
            ttk.Button(self.frm_files, text="Parcourir", command=self.select_unique).pack(pady=3)

        ttk.Label(self.frm_files, text="📊 Nom du fichier Excel :").pack(pady=(10, 0))
        ttk.Entry(self.frm_files, textvariable=self.output_excel, width=55).pack()

    # --- Sélecteurs ---
    def select_recto(self):
        path = filedialog.askopenfilename(filetypes=[("Fichiers PDF", "*.pdf")])
        if path:
            self.pdf_recto.set(path)

    def select_verso(self):
        path = filedialog.askopenfilename(filetypes=[("Fichiers PDF", "*.pdf")])
        if path:
            self.pdf_verso.set(path)

    def select_unique(self):
        path = filedialog.askopenfilename(filetypes=[("Fichiers PDF", "*.pdf")])
        if path:
            self.pdf_unique.set(path)

    # --- Progression ---
    def update_progress(self, value, message):
        self.progress["value"] = value
        self.status_label.config(text=message)
        self.root.update_idletasks()

    # --- Traitement selon le mode ---
    def run_processing(self):
        mode = self.mode.get()
        verifier = self.verifier_traductions.get()
        try:
            if mode == "recto_verso":
                recto, verso, output = self.pdf_recto.get(), self.pdf_verso.get(), self.output_excel.get()
                if not recto or not verso:
                    messagebox.showerror("Erreur", "Merci de sélectionner les deux fichiers PDF.")
                    return
                output_path = imperator(verso, recto, output, progress_callback=self.update_progress)

            elif mode == "combine":
                pdf, output = self.pdf_unique.get(), self.output_excel.get()
                if not pdf:
                    messagebox.showerror("Erreur", "Merci de sélectionner un fichier PDF combiné.")
                    return
                output_path = imperator_combine(pdf, output, progress_callback=self.update_progress)

           

            messagebox.showinfo("Succès", f"Traitement terminé 🎉\nFichier mis à jour : {output_path}")
        except Exception as e:
            messagebox.showerror("Erreur", f"Une erreur est survenue : {e}")

    # --- Envoi vers Anki ---
    def send_to_anki(self):
        excel_anki = self.output_excel_anki.get()
        send_to_anki(
            excel_anki,
            deck_name=self.deck_name.get(),
            model_name=self.model_name.get(),
            field_front=self.field_front.get(),
            field_back=self.field_back.get(),
        )


# --- Lancement ---
if __name__ == "__main__":
    root = tk.Tk()
    app = MistralApp(root)
    root.mainloop()
