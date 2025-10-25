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

# --- Chargement des variables d’environnement ---
load_dotenv()
client = Mistral(api_key=os.getenv("MISTRAL_KEY"))

# 🔹 3 agents différents selon le mode choisi
AGENT_ID_RECTO_VERSO = os.getenv("MISTRAL_AGENT_RECTO_VERSO")
AGENT_ID_COMBINE = os.getenv("MISTRAL_AGENT_COMBINE")
AGENT_ID_MANUEL = os.getenv("MISTRAL_AGENT_MANUEL")

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
            include_image_base64=False,
            agent_id=agent_id
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


# --- Nettoyage et traitement principal ---
def filtrer_lignes_indesirables(lignes):
    motifs = [r"# THÈME", r"# CORRIGÉ", r"exercice", r"partie", r"VOCABULAIRE", r"Chapitre", r"##", r"$=$"]
    return [l for l in lignes if not any(re.search(m, l) for m in motifs)]


def imperator(pdf_verso, pdf_recto, output_excel, progress_callback=None):
    """Mode Recto/Verso"""
    start_time = time.time()
    recto_res = process_pdf_with_mistral(pdf_recto, AGENT_ID_RECTO_VERSO)
    verso_res = process_pdf_with_mistral(pdf_verso, AGENT_ID_RECTO_VERSO)
    recto_lines = filtrer_lignes_indesirables([l.strip() for l in recto_res.split('\n') if l.strip()])
    verso_lines = filtrer_lignes_indesirables([l.strip() for l in verso_res.split('\n') if l.strip()])
    min_len = min(len(recto_lines), len(verso_lines))
    data = [{"Recto": recto_lines[i], "Verso": verso_lines[i]} for i in range(min_len)]
    safe_append_to_excel(data, output_excel)
    elapsed = round(time.time() - start_time, 2)
    progress_callback(100, f"Terminé ✅ ({elapsed}s)")
    return output_excel


def imperator_combine(pdf_combine, output_excel, progress_callback=None):
    """Mode fichier combiné"""
    start_time = time.time()
    res = process_pdf_with_mistral(pdf_combine, AGENT_ID_COMBINE)
    lignes = filtrer_lignes_indesirables([l.strip() for l in res.split('\n') if l.strip()])

    data = []
    for l in lignes:
        if ":" in l:
            parts = l.split(":", 1)
            data.append({"Recto": parts[0].strip(), "Verso": parts[1].strip()})
    safe_append_to_excel(data, output_excel)
    elapsed = round(time.time() - start_time, 2)
    progress_callback(100, f"Terminé ✅ ({elapsed}s)")
    return output_excel


def imperator_manuel(pdf_unique, output_excel, progress_callback=None):
    """Mode Manuel"""
    start_time = time.time()
    res = process_pdf_with_mistral(pdf_unique, AGENT_ID_MANUEL)
    lignes = filtrer_lignes_indesirables([l.strip() for l in res.split('\n') if l.strip()])

    data = []
    for l in lignes:
        if ":" in l:
            parts = l.split(":", 1)
            data.append({"Recto": parts[0].strip(), "Verso": parts[1].strip()})
    safe_append_to_excel(data, output_excel)
    elapsed = round(time.time() - start_time, 2)
    progress_callback(100, f"Terminé ✅ ({elapsed}s)")
    return output_excel


# --- Interface graphique ---
class MistralApp:
    def __init__(self, root):
        self.root = root
        self.root.title("📘 OCR Mistral - Multi Mode + Anki")
        self.root.geometry("600x740")
        self.root.resizable(False, False)

        # --- Variables ---
        self.mode = tk.StringVar(value="recto_verso")
        self.pdf_recto = tk.StringVar()
        self.pdf_verso = tk.StringVar()
        self.pdf_unique = tk.StringVar()
        self.output_excel = tk.StringVar(value="resultats_traitement.xlsx")
        self.output_excel_anki = tk.StringVar(value="cartes_anki.xlsx")

        self.deck_name = tk.StringVar(value="RectoVerso")
        self.model_name = tk.StringVar(value="Basic")
        self.field_front = tk.StringVar(value="Recto")
        self.field_back = tk.StringVar(value="Verso")

        # --- Choix du mode ---
        ttk.Label(root, text="🧩 Sélection du mode :").pack(pady=(10, 5))
        frm_mode = ttk.Frame(root)
        frm_mode.pack()
        for mode, text in [("recto_verso", "Recto/Verso"), ("combine", "Fichier combiné"), ("manuel", "Manuel (1 PDF)")]:
            ttk.Radiobutton(frm_mode, text=text, variable=self.mode, value=mode, command=self.update_file_inputs).pack(side="left", padx=10)

        # --- Zone dynamique ---
        self.frm_files = ttk.Frame(root)
        self.frm_files.pack(pady=10)
        self.update_file_inputs()

        # --- Bouton traitement ---
        ttk.Button(root, text="▶ Lancer le traitement", command=self.run_processing).pack(pady=15)

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

        elif mode == "combine":
            ttk.Label(self.frm_files, text="📄 Sélection du PDF combiné :").pack()
            ttk.Entry(self.frm_files, textvariable=self.pdf_unique, width=55).pack()
            ttk.Button(self.frm_files, text="Parcourir", command=self.select_unique).pack(pady=3)

        elif mode == "manuel":
            ttk.Label(self.frm_files, text="📄 Sélection du PDF manuel :").pack()
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

            elif mode == "manuel":
                pdf, output = self.pdf_unique.get(), self.output_excel.get()
                if not pdf:
                    messagebox.showerror("Erreur", "Merci de sélectionner un fichier PDF pour le mode manuel.")
                    return
                output_path = imperator_manuel(pdf, output, progress_callback=self.update_progress)

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
