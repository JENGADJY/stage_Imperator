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

# --- Chargement des variables d’environnement ---
load_dotenv()
client = Mistral(api_key=os.getenv("MISTRAL_KEY"))
AGENT_ID = os.getenv("MISTRAL_AGENT")

# --- UTILITAIRE EXCEL : append sécurisé ---
def safe_append_to_excel(new_data, output_excel):
    df_new = pd.DataFrame(new_data, columns=["Recto", "Verso"])
    if os.path.exists(output_excel):
        try:
            df_existing = pd.read_excel(output_excel)
            print(f"📂 Ancien fichier détecté : {len(df_existing)} lignes")
            df_combined = pd.concat([df_existing, df_new], ignore_index=True)
        except Exception as e:
            print(f"⚠️ Erreur lors de la lecture du fichier Excel : {e}")
            df_combined = df_new
    else:
        print("📄 Nouveau fichier Excel créé")
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
        print(f"🧩 Traitement des pages {start + 1} à {end}...")
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
        if not ocr_res:
            print(f"⚠️ OCR a échoué pour les pages {start+1}-{end}")
            continue
        pages = getattr(ocr_res, "pages", None) or getattr(ocr_res, "output", None)
        if not pages:
            print(f"⚠️ OCR sans données pour les pages {start+1}-{end}")
            continue
        for page in pages:
            if hasattr(page, "markdown"):
                all_text.append(page.markdown)
            elif isinstance(page, str):
                all_text.append(page)
        print(f"✅ OCR réussi pour les pages {start+1}-{end}")
        try:
            os.remove(temp_path)
        except PermissionError:
            print(f"⚠️ Impossible de supprimer {temp_path} (encore utilisé)")
    return "\n".join(all_text)

# --- Filtrer les lignes indésirables ---
def filtrer_lignes_indesirables(lignes):
    motifs_indesirables = [
        r"# THÈME N \$\{.*\}",  
        r"# CORRIGÉ N \$\{.*\}", 
        r"# premie re partie",  
        r"# \$\w+",  
        r"## Exercices",  
        r"partie", 
    ]

    lignes_filtrees = []
    for ligne in lignes:
        indesirable = False
        for motif in motifs_indesirables:
            if re.search(motif, ligne):
                indesirable = True
                break
        if not indesirable:
            lignes_filtrees.append(ligne)
    return lignes_filtrees

# --- Identifier les lignes non appariées ---
def identifier_lignes_non_appariees(recto_lines, verso_lines):
    min_length = min(len(recto_lines), len(verso_lines))
    lignes_non_appariees = []

    for i in range(min_length):
        if recto_lines[i] != verso_lines[i]:
            lignes_non_appariees.append((i + 1, recto_lines[i], verso_lines[i]))

    # Ajouter les lignes supplémentaires si un fichier est plus long que l'autre
    if len(recto_lines) > min_length:
        for i in range(min_length, len(recto_lines)):
            lignes_non_appariees.append((i + 1, recto_lines[i], "---"))

    if len(verso_lines) > min_length:
        for i in range(min_length, len(verso_lines)):
            lignes_non_appariees.append((i + 1, "---", verso_lines[i]))

    return lignes_non_appariees

# --- Traitement principal ---
def imperator(pdf_verso, pdf_recto, output_excel, progress_callback=None):
    start_time = time.time()
    if progress_callback:
        progress_callback(5, "Lecture du recto...")
    recto_res = process_pdf_with_mistral(pdf_recto)
    if progress_callback:
        progress_callback(35, "Lecture du verso...")
    verso_res = process_pdf_with_mistral(pdf_verso)

    if progress_callback:
        progress_callback(55, "Nettoyage des données...")

    # Nettoyage des lignes
    recto_lines = [line.strip() for line in recto_res.split('\n') if line.strip()]
    verso_lines = [line.strip() for line in verso_res.split('\n') if line.strip()]

    # Filtrer les lignes indésirables
    recto_lines = filtrer_lignes_indesirables(recto_lines)
    verso_lines = filtrer_lignes_indesirables(verso_lines)

    print(f"Nombre de lignes recto après nettoyage : {len(recto_lines)}")
    print(f"Nombre de lignes verso après nettoyage : {len(verso_lines)}")

    # Identifier les lignes non appariées
    lignes_non_appariees = identifier_lignes_non_appariees(recto_lines, verso_lines)

    if lignes_non_appariees:
        print("\nLignes non appariées :")
        for num, recto, verso in lignes_non_appariees:
            print(f"{num} : Recto: {recto} | Verso: {verso}")

    # Vérification de la longueur
    if len(recto_lines) != len(verso_lines):
        print(f"Attention : Le nombre de lignes ne correspond pas. Recto: {len(recto_lines)}, Verso: {len(verso_lines)}")
        min_length = min(len(recto_lines), len(verso_lines))
        recto_lines = recto_lines[:min_length]
        verso_lines = verso_lines[:min_length]

    if progress_callback:
        progress_callback(70, "Appariement des phrases...")

    # Appariement des phrases
    data = []
    for recto, verso in zip(recto_lines, verso_lines):
        data.append({
            "Recto": recto,
            "Verso": verso
        })

    # ✅ Append sécurisé
    safe_append_to_excel(data, output_excel)
    if progress_callback:
        elapsed = round(time.time() - start_time, 2)
        progress_callback(100, f"Terminé ✅ ({elapsed}s)")
    return output_excel

# --- Interface graphique ---
class MistralApp:
    def __init__(self, root):
        self.root = root
        self.root.title("📘 OCR Mistral - Recto/Verso")
        self.root.geometry("520x420")
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
        ttk.Button(root, text="▶ Lancer le traitement", command=self.run_processing).pack(pady=15)
        self.progress = ttk.Progressbar(root, length=350, mode="determinate")
        self.progress.pack(pady=(10, 5))
        self.status_label = ttk.Label(root, text="En attente...")
        self.status_label.pack()

    def select_recto(self):
        path = filedialog.askopenfilename(filetypes=[("Fichiers PDF", "*.pdf")])
        if path:
            self.pdf_recto.set(path)

    def select_verso(self):
        path = filedialog.askopenfilename(filetypes=[("Fichiers PDF", "*.pdf")])
        if path:
            self.pdf_verso.set(path)

    def update_progress(self, value, message):
        self.progress["value"] = value
        self.status_label.config(text=message)
        self.root.update_idletasks()

    def run_processing(self):
        recto = self.pdf_recto.get()
        verso = self.pdf_verso.get()
        output = self.output_excel.get()
        if not recto or not verso:
            messagebox.showerror("Erreur", "Merci de sélectionner les deux fichiers PDF.")
            return
        try:
            output_path = imperator(verso, recto, output, progress_callback=self.update_progress)
            messagebox.showinfo("Succès", f"Traitement terminé 🎉\nFichier mis à jour : {output_path}")
        except Exception as e:
            messagebox.showerror("Erreur", f"Une erreur est survenue : {e}")

# --- Lancement ---
if __name__ == "__main__":
    root = tk.Tk()
    app = MistralApp(root)
    root.mainloop()
