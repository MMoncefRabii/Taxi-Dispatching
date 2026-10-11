# Rapport de stage 2.0.0

Le rapport source est [`rapport_de_stage_2.0.0.tex`](rapport_de_stage_2.0.0.tex). Il ne dépend que de paquets LaTeX standard (dont Babel, TikZ, `booktabs`, `longtable` et `listings`) et contient ses diagrammes en TikZ.

## Compilation

Avec une distribution LaTeX standard et les paquets mentionnés installés :

```powershell
pdflatex -interaction=nonstopmode rapport_de_stage_2.0.0.tex
pdflatex -interaction=nonstopmode rapport_de_stage_2.0.0.tex
```

La seconde passe met à jour la table des matières et les références. Avec XeLaTeX, lancer `xelatex` une fois, puis une seconde fois si les références/table des matières ne sont pas à jour. Une distribution telle que MiKTeX ou TeX Live convient; l'installation automatique de paquets doit être autorisée/configurée au besoin.

Les PDF et fichiers auxiliaires ne sont pas des livrables suivis. Le `.gitignore` local à ce répertoire les exclut. Ne pas ajouter le PDF compilé au dépôt.

## Vérification de cette livraison

Compilation effectuée deux fois avec `pdflatex -interaction=nonstopmode -halt-on-error` sous Windows/MiKTeX. Les deux passes se sont terminées avec le code 0. La dernière a produit un PDF de 17 pages (303 811 octets). Le journal final ne contient aucune erreur fatale, référence ou citation non définie, ni boîte `Overfull`; il contient 181 avertissements typographiques `Underfull \hbox`, principalement liés à la composition des cellules étroites des tableaux. Les avertissements ne sont pas masqués.
