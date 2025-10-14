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
python3 pdf_to_excel.py

```

Créez un fichier `.env` à la racine du projet avec le contenu suivant :

```env

MISTRAL_KEY=

MISTRAL_AGENT=
```

instruction mistral agent :
Je vais t’envoyer soit un seul fichier PDF contenant à la fois les parties recto et verso (le recto dans une langue et le verso dans une autre), soit deux fichiers PDF séparés : l’un avec les phrases dans une langue (recto) et l’autre avec les corrections ou traductions dans une autre langue (verso).

Je veux que tu me retournes chaque phrase du recto avec sa correspondance du verso, dans le format suivant :
1 <phrase recto> | <phrase verso>

Exemple :
1 Ce premier exercice est dédié à Nebrija. En effet c'est cet autre grand découvreur qui écrivit la première grammaire en langue vulgaire. | Este primer ejercicio se dedica a Nebrija. En efecto fue aquel otro gran descubridor quien, en mil cuatrocientos noventa y dos escribió la primera gramática en lengua vulgar.

Je ne veux aucun texte, message ou balise supplémentaire comme "# THÈME N ${ }^{\circ} 5$", "# CORRIGÉ N ${ }^{\circ} 5$", "# première partie", "## Exercices", "partie", etc.
Je veux uniquement les phrases propres, appariées recto/verso, ligne par ligne.
