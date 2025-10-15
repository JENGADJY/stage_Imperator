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
import requests  # 🔥 Pour parler avec AnkiConnect

# --- Chargement des variables d’environnement ---
load_dotenv()
client = Mistral(api_key=os.getenv("MISTRAL_KEY"))
AGENT_ID = os.getenv("MISTRAL_AGENT")

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
def send_to_anki(excel_path, deck_name="RectoVerso"):
    if not os.path.exists(excel_path):
        messagebox.showerror("Erreur", f"Le fichier {excel_path} n’existe pas.")
        return

    if not test_anki_connection():
        messagebox.showerror("Erreur", "AnkiConnect ne répond pas.\nAssure-toi qu’Anki est ouvert et que le module AnkiConnect est installé.")
        return

    df = pd.read_excel(excel_path)
    added = 0

    for _, row in df.iterrows():
        recto = str(row.get("Recto", "")).strip()
        verso = str(row.get("Verso", "")).strip()
        print(f"Recto: '{recto}', Verso: '{verso}'")  # Debug
        if not recto or not verso:
            continue

        payload = {
            "action": "addNote",
            "version": 6,
            "params": {
                "note": {
                    "deckName": deck_name,
                    "modelName": "Basic",
                    "fields": {"Recto": recto, "Verso": verso},
                    "tags": ["auto_import"]
                }
            }
        }
        res = requests.post(ANKI_CONNECT_URL, json=payload).json()
        print(f"Réponse AnkiConnect : {res}")  # Debug
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
    print(f"✅ {len(df_combined)} lignes totales dans {output_excel}")

# --- OCR par lots ---
def process_pdf_with_mistral(pdf_path, pages_per_batch=10):
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

# --- Nettoyage et traitement principal ---
def filtrer_lignes_indesirables(lignes):
    motifs = [r"# THÈME", r"# CORRIGÉ", r"partie", r"##"]
    return [l for l in lignes if not any(re.search(m, l) for m in motifs)]

def imperator(pdf_verso, pdf_recto, output_excel, progress_callback=None):
    start_time = time.time()
    recto_res = process_pdf_with_mistral(pdf_recto)
    verso_res = process_pdf_with_mistral(pdf_verso)
    recto_lines = filtrer_lignes_indesirables([l.strip() for l in recto_res.split('\n') if l.strip()])
    verso_lines = filtrer_lignes_indesirables([l.strip() for l in verso_res.split('\n') if l.strip()])
    min_len = min(len(recto_lines), len(verso_lines))
    data = [{"Recto": recto_lines[i], "Verso": verso_lines[i]} for i in range(min_len)]
    safe_append_to_excel(data, output_excel)
    elapsed = round(time.time() - start_time, 2)
    progress_callback(100, f"Terminé ✅ ({elapsed}s)")
    return output_excel

# --- Interface graphique ---
class MistralApp:
    def __init__(self, root):
        self.root = root
        self.root.title("📘 OCR Mistral - Recto/Verso + Anki")
        self.root.geometry("520x460")
        self.root.resizable(False, False)

        self.pdf_recto = tk.StringVar()
        self.pdf_verso = tk.StringVar()
        self.output_excel = tk.StringVar(value="resultats.xlsx")

        ttk.Label(root, text="Sélection du PDF RECTO :").pack(pady=(20, 5))
        ttk.Entry(root, textvariable=self.pdf_recto, width=55).pack()
        ttk.Button(root, text="Parcourir", command=self.select_recto).pack(pady=5)

        ttk.Label(root, text="Sélection du PDF VERSO :").pack(pady=(10, 5))
        ttk.Entry(root, textvariable=self.pdf_verso, width=55).pack()
        ttk.Button(root, text="Parcourir", command=self.select_verso).pack(pady=5)

        ttk.Label(root, text="Nom du fichier Excel de sortie :").pack(pady=(10, 5))
        ttk.Entry(root, textvariable=self.output_excel, width=55).pack()

        ttk.Button(root, text="▶ Lancer le traitement", command=self.run_processing).pack(pady=10)
        ttk.Button(root, text="📥 Envoyer vers Anki", command=self.send_to_anki).pack(pady=5)

        self.progress = ttk.Progressbar(root, length=350, mode="determinate")
        self.progress.pack(pady=(10, 5))
        self.status_label = ttk.Label(root, text="En attente...")
        self.status_label.pack()

    def select_recto(self):
        path = filedialog.askopenfilename(filetypes=[("Fichiers PDF", "*.pdf")])
        if path: self.pdf_recto.set(path)

    def select_verso(self):
        path = filedialog.askopenfilename(filetypes=[("Fichiers PDF", "*.pdf")])
        if path: self.pdf_verso.set(path)

    def update_progress(self, value, message):
        self.progress["value"] = value
        self.status_label.config(text=message)
        self.root.update_idletasks()

    def run_processing(self):
        recto, verso, output = self.pdf_recto.get(), self.pdf_verso.get(), self.output_excel.get()
        if not recto or not verso:
            messagebox.showerror("Erreur", "Merci de sélectionner les deux fichiers PDF.")
            return
        try:
            output_path = imperator(verso, recto, output, progress_callback=self.update_progress)
            messagebox.showinfo("Succès", f"Traitement terminé 🎉\nFichier mis à jour : {output_path}")
        except Exception as e:
            messagebox.showerror("Erreur", f"Une erreur est survenue : {e}")

    def send_to_anki(self):
        output = self.output_excel.get()
        send_to_anki(output)

# --- Lancement ---
if __name__ == "__main__":
    root = tk.Tk()
    app = MistralApp(root)
    root.mainloop()
