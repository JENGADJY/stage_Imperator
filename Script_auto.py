from mistralai import Mistral
import os
import pandas as pd


client = Mistral(api_key=os.getenv("MISTRAL_KEY"))
AGENT_ID = os.getenv("MISTRAL_AGENT")  

def process_pdf_with_mistral(pdf_path):
    """Upload du PDF et lecture OCR par Mistral"""
    upload_res = client.files.upload(
        file={
            "file_name": os.path.basename(pdf_path),
            "content": open(pdf_path, "rb"),
        },
        purpose="ocr"
    )

    file_id = upload_res.id
    signed = client.files.get_signed_url(file_id=file_id)
    document_url = signed.url

    ocr_res = client.ocr.process(
        model="mistral-ocr-latest",
        document={
            "type": "document_url",
            "document_url": document_url,
        },
        include_image_base64=False
    )
    return ocr_res


def imperator(pdf_verso, pdf_recto, output_excel="resultats.xlsx"):
    """Envoie les deux PDF à ton agent Mistral, récupère la sortie et l’exporte en Excel"""
    
    verso_res = process_pdf_with_mistral(pdf_verso)
    recto_res = process_pdf_with_mistral(pdf_recto)

    text_verso = "\n".join(page.markdown for page in verso_res.pages)
    text_recto = "\n".join(page.markdown for page in recto_res.pages)

    # instructions
    content = f"""


--- RECTO ---
{text_recto}

--- VERSO ---
{text_verso}
    """

    agent_res = client.agents.complete(
        agent_id=AGENT_ID,
        messages=[
            {"role": "user", "content": content}
        ]
    )

    response_text = agent_res.choices[0].message.content.strip()

    # On découpe chaque ligne produite par l’agent
    lines = [line.strip() for line in response_text.split("\n") if line.strip()]

    data = []
    for line in lines:
        
        if "|" in line:
            try:
                num_part, phrases = line.split(" ", 1)
                recto, verso = phrases.split("|", 1)
                data.append({
                    "Numéro": num_part.strip(),
                    "Recto": recto.strip(),
                    "Verso": verso.strip()
                })
            except ValueError:
                # Si la ligne ne correspond pas exactement au format attendu
                data.append({
                    "Numéro": "",
                    "Recto": line,
                    "Verso": ""
                })

    # Création du DataFrame et export Excel
    df = pd.DataFrame(data)
    df.to_excel(output_excel, index=False)

    print(f"✅ Fichier Excel généré : {output_excel}")
    return df



