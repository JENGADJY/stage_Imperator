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
```

instruction mistral agent :
Je vais t’envoyer 

Soit un seul fichier PDF contenant à la fois les parties de thèmes d'application avec recto qui sera le langue 1 et verso qui sera la langue 2 .

Soit deux fichiers PDF séparés : l’un avec les phrases dans une langue (recto) et l’autre avec les corrections ou traductions dans une autre langue (verso).

Je veux que tu me retournes chaque phrase du recto avec sa correspondance du verso, dans le format suivant :
1 <phrase recto> | <phrase verso>

Exemple :
1 Ce premier exercice est dédié à Nebrija. En effet c'est cet autre grand découvreur qui écrivit la première grammaire en langue vulgaire. | Este primer ejercicio se dedica a Nebrija. En efecto fue aquel otro gran descubridor quien, en mil cuatrocientos noventa y dos escribió la primera gramática en lengua vulgar.

Information: 
-Genralement La fin d'une fin est delimiter par un point mais il y a des execeptions car il y a deux phrases dans une exemple ducoup ils restent ensemble .
-Je ne veux aucun texte, message ou balise supplémentaire comme "# THÈME N ${ }^{\circ} 5$", "# CORRIGÉ N ${ }^{\circ} 5$", "# première partie", "## Exercices", "partie", etc.
Je veux uniquement les phrases propres, appariées recto/verso, ligne par ligne.
-Les nom des sections sont juste des rappels car les images proviennent d'un livre. Donc Veuillez ne pas les inscrire (exemple: "theme d'application") .