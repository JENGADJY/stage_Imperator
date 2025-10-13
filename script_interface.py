import os
import tkinter as tk
from tkinter import filedialog, messagebox
from tkinter import ttk
import pandas as pd
from mistralai import Mistral
from PyPDF2 import PdfReader
import tempfile
# Chargement des variables d’environnement
from dotenv import load_dotenv
load_dotenv()

client = Mistral(api_key=os.getenv("MISTRAL_KEY"))
AGENT_ID = os.getenv("MISTRAL_AGENT")

# --- FONCTIONS MÉTIER ---

def process_pdf_with_mistral(pdf_path, pages_per_batch=10):
    """
    OCR multi-pages : découpe le PDF en blocs de `pages_per_batch` pages
    et concatène les résultats OCR.
    """
    reader = PdfReader(pdf_path)
    total_pages = len(reader.pages)
    all_text = []
    from PyPDF2 import PdfWriter

    for start in range(0, total_pages, pages_per_batch):
        end = min(start + pages_per_batch, total_pages)
        print(f"🧩 Traitement des pages {start + 1} à {end}...")

        # Créer un fichier PDF temporaire pour ces pages
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as temp_pdf:
            pdf_writer = PdfWriter()
            for i in range(start, end):
                pdf_writer.add_page(reader.pages[i])
            pdf_writer.write(temp_pdf)
            temp_path = temp_pdf.name  # On garde le chemin

        # ✅ Fichier fermé, on peut l’utiliser
        with open(temp_path, "rb") as f:
            upload_res = client.files.upload(
                file={
                    "file_name": f"chunk_{start+1}_to_{end}.pdf",
                    "content": f,
                },
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

        # ✅ Vérifications
        if not ocr_res:
            print(f"⚠️ OCR a échoué pour les pages {start+1}-{end} (aucune réponse reçue)")
            continue

        pages = getattr(ocr_res, "pages", None) or getattr(ocr_res, "output", None)

        if not pages:
            print(f"⚠️ OCR a échoué pour les pages {start+1}-{end} (aucune donnée dans la réponse)")
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



def imperator(pdf_verso, pdf_recto, output_excel, progress_callback=None):
    """Analyse des deux PDF et export Excel"""
    if progress_callback:
        progress_callback(10, "Lecture du recto...")

    verso_res = process_pdf_with_mistral(pdf_verso)
    if progress_callback:
        progress_callback(40, "Lecture du verso...")

    recto_res = process_pdf_with_mistral(pdf_recto)
    if progress_callback:
        progress_callback(60, "Envoi à l’agent Mistral...")

    text_verso = verso_res
    text_recto = recto_res

    # Envoi à ton agent Mistral
    content = f"""
Voici deux documents PDF à traiter selon tes instructions :

--- RECTO ---
{text_recto}

--- VERSO ---
{text_verso}
    """

    agent_res = client.agents.complete(
        agent_id=AGENT_ID,
        messages=[{"role": "user", "content": content}]
    )

    response_text = agent_res.choices[0].message.content.strip()
    if progress_callback:
        progress_callback(80, "Analyse de la réponse...")

    # Parsing du texte en lignes
    lines = [line.strip() for line in response_text.split("\n") if "|" in line]
    data = []
    for line in lines:
        try:
            num_part, phrases = line.split(" ", 1)
            recto, verso = phrases.split("|", 1)
            data.append({
                "Numéro": num_part.strip(),
                "Recto":  recto.strip(),
                "Verso": verso.strip()
            })
        except ValueError:
            data.append({"Numéro": "", "Recto": line, "Verso": ""})

    df = pd.DataFrame(data)
    df.to_excel(output_excel, index=False)

    if progress_callback:
        progress_callback(100, "Terminé ✅")
    return output_excel


# --- INTERFACE TKINTER ---

class MistralApp:
    def __init__(self, root):
        self.root = root
        self.root.title("📘 OCR Mistral - Recto/Verso")
        self.root.geometry("500x400")
        self.root.resizable(False, False)

        self.pdf_recto = tk.StringVar()
        self.pdf_verso = tk.StringVar()
        self.output_excel = tk.StringVar(value="resultats.xlsx")

        ttk.Label(root, text="Sélection du PDF RECTO :").pack(pady=(20, 5))
        ttk.Entry(root, textvariable=self.pdf_recto, width=50).pack()
        ttk.Button(root, text="Parcourir", command=self.select_recto).pack(pady=5)

        ttk.Label(root, text="Sélection du PDF VERSO :").pack(pady=(10, 5))
        ttk.Entry(root, textvariable=self.pdf_verso, width=50).pack()
        ttk.Button(root, text="Parcourir", command=self.select_verso).pack(pady=5)

        ttk.Label(root, text="Nom du fichier Excel de sortie :").pack(pady=(10, 5))
        ttk.Entry(root, textvariable=self.output_excel, width=50).pack()

        ttk.Button(root, text="▶ Lancer le traitement", command=self.run_processing).pack(pady=15)

        self.progress = ttk.Progressbar(root, length=300, mode="determinate")
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
            messagebox.showinfo("Succès", f"Traitement terminé 🎉\nFichier créé : {output_path}")
        except Exception as e:
            messagebox.showerror("Erreur", f"Une erreur est survenue : {e}")


# --- LANCEMENT DE L’APPLICATION ---
if __name__ == "__main__":
    root = tk.Tk()
    app = MistralApp(root)
    root.mainloop()
