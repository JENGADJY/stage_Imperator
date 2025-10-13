```env

git init
git clone 
```





Créez un fichier `.env` à la racine du projet avec le contenu suivant :

```env

MISTRAL_KEY=

MISTRAL_AGENT=
```

instruction mistral agent :
Je vais t'envoyer deux fichiers pdf . L'un des deux pdf contiendra des phrases en français étant tirés d'une pages d'un livre qui sera seulement le côté recto et l'autre pdf sera le côté verso qui la correction de ses phrases dans une langues differentes. peux-tu me les retourner en sachant que chaque phrases a ca correction en prenant en compte le recto verso . je veux donc que tu me retourne un lle numero de la phrase ainsi que la phase recto ensuite suivi de "|" qui sert de délimiteur et ensuite me mettre le verso . je veux juste que tu me les sorte en ligne de code simple du genre : " 1 Ce premier exercice est dédié à Nebrija. En effet c'est cet autre grand découvreur qui écrivit la première grammaire en langue vulgaire. | Este primer ejercicio se dedica a Nebrija. En efecto fue aquel otro gran descubridor quien, en mil cuatrocientos noventa y dos escribió la primera gramática en lengua vulgar. "
