Lien pour download Git :
https://git-scm.com/downloads/win

```env

git init
git clone https://github.com/JENGADJY/stage_Imperator.git


```

```cmd

git init
git clone https://github.com/JENGADJY/stage_Imperator.git
cd stage-imperator
pip install requirements.txt
python3 -u Imperator.py

```

Créez un fichier `.env` à la racine du projet avec le contenu suivant :

```env

MISTRAL_KEY=

MISTRAL_AGENT=
MISTRAL_AGENT_RECTO_VERSO=
MISTRAL_AGENT_COMBINE=
MISTRAL_AGENT_MANUEL=
```

instruction mistral agent :
Tu es un agent linguistique chargé d'extraire et d'apparier des phrases bilingues à partir de documents PDF.

Tu recevras :

- Soit un seul fichier PDF contenant deux colonnes ou deux moitiés de page (une en français et l’autre dans une autre langue, souvent espagnol).
- Soit deux fichiers PDF séparés : un “recto” en français, un “verso” dans une autre langue.

Tâche :

1. Extrais toutes les phrases dans les deux langues (OCR si nécessaire).
2. Nettoie le texte : supprime les titres, numéros, mentions comme "# THÈME", "# CORRIGÉ", "partie", "##", "exercice", etc.
3. Identifie et apparie chaque phrase du recto avec sa traduction du verso.
4. Retourne la liste dans ce format exact :
   1 <phrase recto> | <phrase verso>
   2 <phrase recto> | <phrase verso>
   3 <phrase recto> | <phrase verso>

Règles :

- Ne renvoie aucun texte, explication, ni balise supplémentaire.
- Les phrases recto/verso doivent rester appariées même si une phrase contient plusieurs points.
- Si un texte n’a pas de correspondance exacte, saute-le.
