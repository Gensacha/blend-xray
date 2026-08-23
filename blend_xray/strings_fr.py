# SPDX-License-Identifier: GPL-3.0-or-later
"""French string catalogue. Data only -- the machinery lives in :mod:`strings`.

First translation, and the one that matters most: the audience is the
international Blender community, but the author teaches VFX to French
students. Written for artists who do not read code -- plain words over jargon
wherever a plain word exists.

Deliberately left in English, in the French text as well:

  * Blender's own on-screen UI labels: "Auto Run Python Scripts",
    "Preferences > Save & Load" -- that is what is printed on screen.
  * Blender's own source-code comment quoted verbatim in text_autorun_flag.
  * Code-level identifiers: TXT_ISSCRIPT, TXT_ISMEM, DRIVER_FLAG_USE_SELF,
    NODE_SCRIPT_INTERNAL/EXTERNAL, bpy.types.Panel, register()/unregister().
  * A handful of terms that French VFX/Blender practice keeps in English day
    to day rather than translating -- "driver", "datablock", "OSL", "flags" --
    the same way "rig" or "shader" stay English in French production French.
    Translating these would make the report harder for the target reader to
    map back onto what they see in Blender, not easier.

The banned words here are "sûr", "sain", "propre" and "sans danger": the
direct equivalents of "safe" and "clean". They appear nowhere below, not even
negated. See ``tests/conftest.py::BANNED_WORDS_BY_LANG``.
"""

from __future__ import annotations

from typing import Final

FR: Final[dict[str, str]] = {
    # -- tool identity -----------------------------------------------------
    "tool_name": "Blend X-Ray",
    "tool_tagline": "Fait l'inventaire du code caché dans un fichier .blend, sans ouvrir Blender.",
    "never_runs": "Blend X-Ray ne lance jamais Blender et n'exécute jamais rien de ce qu'il trouve.",
    # -- scan lifecycle ----------------------------------------------------
    "scanning_file": "Analyse : {path}",
    "scanned_n_files": "{count} fichier(s) analysé(s).",
    "no_files_matched": "Aucun fichier .blend ne correspond à : {target}",
    # -- the inventory framing (never a verdict) ---------------------------
    "categories_checked_header": "{count} catégories vérifiées :",
    "scan_timed_out_notice": (
        "INSPECTION PARTIELLE -- le budget de {limit} seconde(s) a expiré pendant "
        "la lecture de : {stage}. Tout ce qui suit ne décrit que la partie du "
        "fichier lue avant cet arrêt."
    ),
    "stage_text": "les blocs de texte Python",
    "stage_driver": "les expressions de driver",
    "stage_osl": "les nœuds OSL / script",
    "stage_library": "les bibliothèques liées",
    "stage_filepath": "les autres chemins de fichier",
    "stage_preflight": "la structure du fichier",
    "nothing_found": (
        "Aucun code intégré trouvé dans les catégories vérifiées. Cela décrit ce "
        "que Blend X-Ray a cherché, rien de plus -- l'outil ne connaît que les "
        "catégories listées ci-dessus, alors considérez ceci comme un inventaire, "
        "pas comme un feu vert."
    ),
    "findings_header": "{summary} trouvé(s). Les voici :",
    "not_a_verdict": (
        "Ceci est un inventaire, pas un verdict. Blend X-Ray rapporte ce qui se "
        "trouve dans le fichier ; décider de lui faire confiance vous appartient."
    ),
    # -- the one-glance banner ---------------------------------------------
    "banner_red_headline": "Ce fichier contient du code qui sort de Blender.",
    "banner_amber_headline": "Ce fichier contient du code qui mérite un deuxième regard.",
    "banner_neutral_headline": "Rien trouvé dans les {count} catégories vérifiées.",
    "banner_neutral_headline_accounted": (
        "Rien qui sorte de Blender, dans les {count} catégories vérifiées."
    ),
    "banner_timeout_headline": (
        "Blend X-Ray a manqué de temps sur ce fichier. Ce qui suit est une "
        "inspection partielle."
    ),
    "banner_sentence": "Il {actions}.",
    "banner_join_and": "et",
    "banner_recognised": (
        "Une partie de ce code est enregistrée comme appartenant à une version publiée "
        "({names}). C'est indiqué ici ; ce n'est pas une raison de retirer de votre écran "
        "la ligne ci-dessus."
    ),
    "banner_neutral_not_clearance": (
        "Ce n'est pas un feu vert. Cela décrit ce qui a été examiné, et rien au-delà."
    ),
    "banner_neutral_checked": "Examiné : {categories}",
    # -- banner: what was found, in words an artist can picture ------------
    "banner_what_x_network": "contacte Internet",
    "banner_what_x_subprocess": "lance un programme sur votre machine",
    "banner_what_x_living_off_land": "pilote un outil intégré du système pour exécuter des commandes",
    "banner_what_x_obfuscation": "décode quelque chose puis exécute le résultat comme du code",
    "banner_what_x_opaque_blob": "transporte un long bloc de données encodées",
    "banner_what_x_persistence": "s'inscrit à un endroit qui démarre avec votre système",
    "banner_what_x_credentials": "lit là où sont rangés les mots de passe et les portefeuilles crypto",
    "banner_what_x_lowlevel": "descend dans votre système d'exploitation à bas niveau",
    "banner_what_library_unc": "pointe vers un fichier sur un partage réseau",
    "banner_what_x_network_listen": "ouvre un port auquel d'autres machines peuvent se connecter",
    "banner_what_x_builtins_indirection": "atteint les fonctions intégrées de Python à l'exécution",
    "banner_what_x_indirect_call": "exécute ce qu'un autre appel lui a renvoyé",
    "banner_what_x_assembled_name": "assemble en morceaux le nom de ce qu'il appelle",
    "banner_what_x_dynamic_code": "fabrique et exécute du code pendant qu'il tourne",
    "banner_what_x_file_write": "écrit des fichiers",
    "banner_what_x_file_delete": "supprime des fichiers",
    "banner_what_x_makedirs": "crée des dossiers",
    "banner_what_x_compile_code": "transforme du texte en code exécutable",
    "banner_what_x_deserialise": "lit des données Python capables d'exécuter du code au chargement",
    "banner_what_x_runtime_import": "charge un module par son nom pendant qu'il tourne",
    "banner_what_x_opens_browser": "ouvre une adresse web dans votre navigateur",
    "banner_what_x_decodes_data": "décode ou décompresse les données qu'il transporte",
    "banner_what_x_split_literal": "fabrique du texte à partir de morceaux séparés",
    "banner_what_x_handler_persist": "installe un handler qui reste actif après l'ouverture d'autres fichiers",
    "banner_what_x_handler_register": "installe un handler qui s'exécute sur les événements de Blender",
    "banner_what_driver_code": "contient une expression de driver qui exécute du Python",
    "banner_what_library_drive_letter": "pointe vers un fichier par une lettre de lecteur fixe",
    "banner_what_driver_not_simple": "contient une expression de driver qui a besoin de Python complet",
    "banner_what_osl_bytecode": "transporte du bytecode de shader précompilé",
    "banner_what_autorun_unrecognised": "est réglé pour exécuter un script dès l'ouverture du fichier",
    "banner_what_unreadable_script": "contient un script que Blend X-Ray n'a pas pu lire",
    "banner_what_scan_timed_out": "a demandé plus de temps d'inspection que le budget alloué",
    # -- closing recommendation --------------------------------------------
    "recommend_header": "Recommandation",
    "recommend_needs_human": (
        "Ce fichier contient du code que Blend X-Ray ne peut pas juger à votre place. "
        "Avant de l'ouvrir dans Blender, demandez à quelqu'un qui lit le Python de "
        "regarder les blocs signalés ci-dessus. Si personne ne peut le faire, "
        "laissez le fichier fermé -- aucun asset ne vaut une machine compromise."
    ),
    "recommend_looks_ordinary": (
        "Rien ici ne correspond aux motifs que Blend X-Ray traite comme alarmants, et "
        "les éléments trouvés ci-dessus sont du genre que contient un fichier "
        "d'asset ou de rig ordinaire. Cela décrit ce qui a été trouvé et ne "
        "promet rien de plus, alors lisez-les vous-même en cas de doute."
    ),
    "recommend_known_release": (
        "Le code signalé dans ce fichier est enregistré comme appartenant à une version "
        "publiée, nommé bloc par bloc ci-dessus avec l'origine d'où il a été relevé. Rien "
        "n'a été retiré de la liste et rien n'a été atténué. Ce n'est pas soumis à votre "
        "relecture parce que ce n'est pas un script que vous seul pouvez vérifier -- c'est "
        "un script que beaucoup de gens ont déjà téléchargé et lu. Ce qu'il vous reste à "
        "juger, c'est l'origine indiquée ci-dessus : si ce n'est pas un endroit d'où vous "
        "prendriez sciemment un fichier, traitez-le comme n'importe quel script non lu."
    ),
    "recommend_timed_out": (
        "Cette inspection s'est arrêtée avant la fin. Blend X-Ray a atteint son "
        "budget de {limit} seconde(s) pendant la lecture de : {stage}, et n'a pas "
        "regardé le reste du fichier ; rien de ce qui précède ne décrit donc ce que "
        "contient la partie non atteinte. Relancez avec --max-seconds plus grand, "
        "ou considérez ce fichier comme non inspecté."
    ),
    "recommend_autorun_present": (
        "Au moins un script de ce fichier est marqué pour s'exécuter "
        "automatiquement dès l'ouverture du fichier. Laissez « Auto Run Python "
        "Scripts » désactivé dans Preferences > Save & Load tant que vous n'avez "
        "pas lu ce script."
    ),
    "recommend_unreadable": (
        "Blend X-Ray n'a pas réussi à lire {count} script(s) de ce fichier : "
        "aucune de ses vérifications ne leur a été appliquée, et rien de ce qui "
        "précède ne décrit ce qu'ils font. C'est un angle mort de l'inspection, "
        "pas un résultat. Lisez-les vous-même, ou faites-les lire."
    ),
    # -- category labels ---------------------------------------------------
    "cat_text": "Blocs de texte Python (scripts à exécution automatique)",
    "cat_driver": "Expressions de driver",
    "cat_osl": "OSL / nœuds de script",
    "cat_library": "Bibliothèques liées",
    "cat_filepath": "Autres chemins de fichiers de datablocks",
    # -- text datablocks ---------------------------------------------------
    "text_block_title": "Bloc de texte : {name}",
    "text_autorun_flag": (
        "MARQUÉ AUTO-RUN (TXT_ISSCRIPT). Le commentaire de Blender pour ce flag "
        'est : "Load the script as a Python module when loading the .blend '
        'file." C\'est le flag utilisé par la campagne CGTrader de novembre 2025.'
    ),
    "text_not_autorun": "Pas marqué auto-run (TXT_ISSCRIPT n'est pas défini).",
    "text_flags": "Flags : {flags}",
    "text_filepath": "Chemin du fichier texte : {path}",
    "text_is_mem": "TXT_ISMEM défini : le texte est stocké dans le .blend, pas sur le disque.",
    "text_is_ext": "TXT_ISEXT défini : le texte est censé provenir d'un fichier externe.",
    "text_source_header": "Source :",
    "text_truncated": "-- tronqué à {shown} caractères sur {total} ; relancez avec --full pour tout voir --",
    "text_empty": "(ce bloc de texte est vide)",
    # -- drivers -----------------------------------------------------------
    "driver_title": "Expression de driver sur {owner}",
    "driver_type": "Type de driver : {type_name}",
    "driver_expression": "Expression : {expr}",
    "driver_simple": (
        "Ressemble à une simple expression arithmétique. Blender évalue ce type "
        "d'expression dans un évaluateur interne restreint (sans Python), donc "
        "elle fonctionne même avec l'auto-exécution de Python désactivée."
    ),
    "driver_suspicious": (
        "Utilise des noms hors de l'évaluateur restreint, donc elle a besoin de "
        "Python complet -- ce qui veut dire qu'elle ne s'exécute que si "
        "l'auto-exécution des scripts est activée. Vaut le coup d'être lue."
    ),
    # Affiché à la place des deux lignes ci-dessus quand le type du driver fait
    # que Blender ne lit jamais le champ expression. evaluate_driver() envoie
    # AVERAGE et SUM vers evaluate_driver_sum(), MIN/MAX vers
    # evaluate_driver_min_max() ; seul DRIVER_TYPE_PYTHON atteint l'expression.
    "driver_expression_unused": (
        "Blender n'utilise pas ce texte. Un driver {type_name} est calculé à partir "
        "des valeurs de ses entrées, et le champ expression n'est jamais lu pour lui. "
        "Il est affiché parce qu'il est stocké dans le fichier, pas parce qu'il s'exécute."
    ),
    "driver_use_self": (
        "DRIVER_FLAG_USE_SELF est défini : l'expression peut accéder à l'objet qu'elle pilote."
    ),
    "driver_flags": "Flags de driver : {flags}",
    # -- OSL / script nodes ------------------------------------------------
    "osl_title": "Nœud de script dans l'arbre de nœuds : {owner}",
    "osl_lower_severity": (
        "Sévérité moindre : les nœuds de script OSL sont réservés à Cycles, OSL "
        "est désactivé par défaut, et ils s'exécutent au moment du rendu -- pas "
        "à l'ouverture du fichier. Ce n'est pas un vecteur d'auto-exécution."
    ),
    # Voir la note dans strings_en.py : « nommé ci-dessous » promettait un nom
    # qu'aucune surface n'affichait et que NodeShaderScript ne porte pas.
    "osl_internal": (
        "mode = NODE_SCRIPT_INTERNAL : le code provient d'un bloc de texte "
        "stocké dans ce fichier. L'enregistrement du nœud ne porte pas le nom "
        "de ce bloc : regardez les blocs de texte listés dans ce rapport."
    ),
    "osl_external": "mode = NODE_SCRIPT_EXTERNAL : le code provient d'un fichier externe.",
    "osl_filepath": "Chemin du nœud de script : {path}",
    "osl_has_bytecode": "Ce nœud contient {size} octets de bytecode précompilé.",
    "osl_bytecode_hash": "Empreinte du bytecode : {hash}",
    # -- libraries ---------------------------------------------------------
    "library_title": "Bibliothèque liée : {path}",
    "library_relative": "Chemin relatif au .blend (« // »), résolu en : {resolved}",
    # Voir la note dans strings_en.py : l'ancienne formulation affirmait une
    # position (« pointe hors du dossier du fichier ») qui n'avait jamais été
    # vérifiée. Seule la seconde clé revendique un contenant, et seulement
    # quand une comparaison de texte l'a établi.
    "library_absolute": (
        "CHEMIN ABSOLU -- désigne un emplacement fixe sur la machine qui a "
        "enregistré le fichier, pas un emplacement relatif au .blend."
    ),
    "library_absolute_inside": (
        "CHEMIN ABSOLU -- désigne un emplacement fixe sur la machine qui a "
        "enregistré le fichier. Écrit tel quel, il tombe à l'intérieur du "
        "dossier de ce fichier."
    ),
    "library_escapes": "LE CHEMIN SORT du dossier du fichier via « .. » -- résolu en : {resolved}",
    "library_unc": "CHEMIN RÉSEAU UNC -- pointe vers un partage réseau ({host}).",
    "library_disguised": (
        "ÉCRIT POUR RESSEMBLER À UN LIEN ORDINAIRE -- ce chemin commence par le "
        "marqueur « // » de Blender, qui veut normalement dire « à côté de ce "
        "fichier .blend », mais il porte des séparateurs supplémentaires qui le "
        "font pointer vers une racine à lui."
    ),
    "library_drive": (
        "CHEMIN AVEC LETTRE DE LECTEUR -- pointe vers un lecteur précis sur la "
        "machine de la personne qui ouvre le fichier."
    ),
    "library_ok_relative": "Reste à l'intérieur du dossier du fichier.",
    # -- other filepaths ---------------------------------------------------
    "filepath_title": "{kind} : {name}",
    "filepath_value": "  chemin : {path}",
    "filepath_informational": (
        "À titre indicatif uniquement. Ce sont les fichiers externes que le "
        ".blend s'attend à charger. Un chemin pointant vers un partage réseau ou "
        "une autre machine mérite d'être regardé de plus près."
    ),
    # -- explanation layer -------------------------------------------------
    "explain_header": "Ce que fait ce code, en langage clair :",
    "explain_evidence": "(preuve : {evidence})",
    "explain_literals_header": "Chaînes de texte trouvées dans le code (URLs, chemins, commandes) :",
    "explain_no_literals": (
        "Aucune URL, aucun chemin ni aucune commande shell n'a été trouvé en texte brut dans ce code."
    ),
    "explain_unparseable": (
        "Ce code n'a pas pu être interprété comme du Python, donc Blend X-Ray n'a "
        "pas pu en analyser la structure. Raison : {reason}. Recherche en texte "
        "brut utilisée à la place."
    ),
    "explain_too_large": (
        "Ce code fait {size} octets, ce qui dépasse la limite d'analyse de "
        "{limit} octets, donc Blend X-Ray ne l'a pas interprété. Le texte brut "
        "reste affiché ci-dessous."
    ),
    "explain_parse_exhausted": (
        "L'analyse de ce code a épuisé l'interpréteur Python (il est imbriqué de "
        "façon extrême). C'est inhabituel pour du code écrit à la main, et ce "
        "fait mérite d'être noté en soi."
    ),
    "explain_obfuscated_honest": (
        "Je ne peux pas vous dire ce que fait ce code, parce qu'il est "
        "délibérément dissimulé. C'est en soi le signal le plus fort ici."
    ),
    "explain_obfuscated_partial": (
        "Une partie de ce code est délibérément dissimulée et ne devient lisible "
        "qu'à l'exécution, donc la liste ci-dessus est incomplète -- Blend X-Ray ne "
        "peut pas voir la partie cachée. Un script de rig ou d'asset légitime n'a "
        "aucune raison de cacher quoi que ce soit."
    ),
    "explain_nothing_notable": (
        "Rien dans ce code ne correspond à un comportement que Blend X-Ray sait "
        "décrire. Cela ne veut pas dire qu'il ne fait rien -- cela veut dire "
        "que Blend X-Ray n'a pas de règle pour ça. Lisez-le vous-même, ou demandez à "
        "quelqu'un qui lit le Python."
    ),
    "explain_baseline": (
        "Pour comparaison : un script de rig ou d'asset légitime définit "
        "normalement des panneaux d'interface et des opérateurs (des classes "
        "héritant de bpy.types.Panel ou bpy.types.Operator), les enregistre dans "
        "register()/unregister(), et ne touche à rien en dehors de Blender. Il "
        "n'a aucune raison d'ouvrir une connexion réseau, de lancer un programme, "
        "ou de décoder un bloc caché."
    ),
    # -- explanation rules -------------------------------------------------
    "x_import_geometry": "importe de la géométrie 3D",
    "x_ui_panel": (
        "définit un panneau d'interface ou un opérateur -- c'est à ça que ressemble un script de rig normal"
    ),
    "x_register": "enregistre ses panneaux et opérateurs auprès de Blender (normal pour un add-on ou un rig)",
    "x_driver_namespace": "enregistre des fonctions utilitaires de driver utilisées par un rig",
    "x_file_write": "écrit des fichiers sur le disque",
    "x_file_delete": "supprime des fichiers",
    "x_makedirs": "crée des dossiers sur le disque",
    # Deux phrases pour les handlers, parce que Blender traite les deux cas
    # différemment : seul un callback portant @persistent survit à l'ouverture
    # du fichier suivant, les autres sont retirés par BPY_app_handlers_reset(false)
    # avant même que les scripts du nouveau fichier ne s'exécutent.
    "x_handler_persist": (
        "installe un handler marqué @persistent : il continue donc de s'exécuter sur chaque "
        "fichier que vous ouvrirez ensuite, pas seulement celui-ci"
    ),
    "x_handler_register": (
        "se greffe sur les événements de Blender -- changement d'image, ouverture de fichier -- "
        "et s'exécute à chacun d'eux, jusqu'à ce que vous ouvriez un autre fichier"
    ),
    "x_compile_code": (
        "transforme du texte en code exécutable sans l'exécuter ; il faut autre chose pour lancer le résultat"
    ),
    "x_deserialise": (
        "lit des données Python enregistrées dans un format capable d'exécuter du code pendant la "
        "lecture : ce qui s'exécute dépend du fichier de données, pas de ce script"
    ),
    "x_runtime_import": (
        "charge un module par son nom pendant qu'il tourne ; le nom est écrit dans le fichier, "
        "vous pouvez donc voir lequel"
    ),
    "x_opens_browser": "transmet une adresse web à votre navigateur pour qu'il l'ouvre",
    "x_decodes_data": (
        "remet des données encodées ou compressées dans leur forme d'origine : vous ne pouvez donc "
        "pas lire ces données directement dans le fichier"
    ),
    "x_split_literal": (
        "fabrique du texte en collant des morceaux, ce qui garde le texte final hors de portée "
        "d'une recherche dans le fichier"
    ),
    "x_network": "se connecte à internet",
    "x_network_listen": (
        "ouvre un port sur votre machine, auquel d'autres machines peuvent se connecter"
    ),
    "x_subprocess": "lance un programme externe sur votre machine",
    "x_living_off_land": (
        "lance un outil système Windows couramment utilisé pour télécharger et exécuter des programmes ({tools})"
    ),
    "x_dynamic_code": (
        "construit et exécute du code pendant qu'il tourne, donc ce qu'il fait n'est pas visible dans le fichier"
    ),
    # Dit ce qui a été établi -- une valeur décodée qui arrive jusqu'à une
    # exécution -- et pas la conclusion à laquelle sautait l'ancienne phrase.
    # L'ancienne formulation (« le contenu est délibérément dissimulé »)
    # s'imprimait dès qu'un décodage et un exec apparaissaient dans le même
    # fichier, ce qui sur de vrais add-ons est couramment sans rapport.
    "x_obfuscation": (
        "décode des données puis exécute le résultat comme du code : ce qu'il fait vraiment "
        "n'est écrit nulle part dans le fichier"
    ),
    # Les trois formes de dissimulation. Chacune dit ce que le code met en
    # place, jamais ce qu'il fera : une fois les noms partis, cela ne peut plus
    # se savoir, et le prétendre serait la supposition que cet outil refuse.
    "x_builtins_indirection": (
        "atteint les fonctions intégrées de Python par leur nom à l'exécution, ce qui garde "
        "le nom de ce qu'il utilise hors du fichier"
    ),
    "x_indirect_call": (
        "exécute ce qu'un autre appel lui a renvoyé : le nom de ce qu'il lance finalement "
        "n'est écrit nulle part dans le fichier"
    ),
    "x_assembled_name": (
        "assemble en morceaux le nom de ce qu'il charge ou appelle, si bien que ce nom "
        "n'apparaît nulle part dans le fichier"
    ),
    "x_opaque_blob": (
        "contient un bloc de texte encodé de {size} caractères, ce dont un script normal n'a pas besoin"
    ),
    "x_persistence": "se programme pour redémarrer automatiquement",
    "x_lowlevel": "appelle des fonctions système bas niveau",
    "x_credentials": "lit des emplacements où sont stockés des mots de passe ou des portefeuilles",
    # Literal kinds.
    "lit_url": "URL",
    "lit_host": "nom d'hôte",
    "lit_path": "chemin de fichier",
    "lit_command": "commande shell",
    "lit_blob": "bloc encodé",
    # -- couche d'identité des scripts connus ------------------------------
    "identity_header": "Identité",
    "identity_line": "{script_name} -- {origin}",
    "identity_evidence_byte": (
        "Preuve : chaque octet de ce bloc est identique à une copie de référence "
        "enregistrée par Blend X-Ray. C'est la correspondance la plus forte que cette base "
        "puisse établir -- changez un seul caractère n'importe où dans le script et elle "
        "ne correspond plus."
    ),
    "identity_evidence_structure": (
        "Preuve : le code est agencé exactement comme une copie de référence, mais le "
        "texte entre guillemets, lui, diffère. La correspondance est plus faible, et elle "
        "l'est du mauvais côté : celui qui modifie ce script peut laisser la structure "
        "intacte et ne changer que le texte entre guillemets, là où se logerait une adresse "
        "de téléchargement. Chaque différence est listée ci-dessous, et ce bloc continue de "
        "compter dans la recommandation."
    ),
    "identity_generated_byte": (
        "Ce script est réécrit à neuf pour chaque rig : le faire correspondre octet par "
        "octet identifie cette copie générée-là -- pas une version publiée que beaucoup de "
        "gens partagent et ont lue entre eux. Il reste dans la liste, à faire regarder."
    ),
    "identity_source": "Copie de référence relevée sur : {url} (récupérée le {fetched_on})",
    "identity_attested": (
        "Attesté par {attested_by} le {attested_on}. C'est la parole d'une seule personne "
        "affirmant que cette empreinte correspond à ce script -- pas une relecture de ce "
        "que le script fait."
    ),
    "identity_notes": "Ce qu'est ce script : {notes}",
    "identity_scope": (
        "Ceci dit ce qu'est le bloc, pas ce qu'il vaut. Tout ce qui est listé plus haut a "
        "bien été trouvé dedans, à la gravité où cela a été trouvé."
    ),
    "identity_diff_header": (
        "Texte entre guillemets qui diffère de la copie de référence ({count}) :"
    ),
    "identity_diff_line": "#{index} : en référence {reference} -> dans ce fichier {actual}",
    "identity_diff_more": "... et {count} différence(s) supplémentaire(s) non affichée(s).",
    "identity_diff_none": (
        "Aucun texte entre guillemets ne diffère. Les deux copies ne s'écartent que par "
        "l'espacement, les commentaires ou l'ordre des lignes."
    ),
    "identity_db_missing": (
        "La base des scripts connus n'est pas à {path} : aucun bloc n'a été confronté à "
        "elle. Tout le reste de ce rapport a été produit normalement."
    ),
    "identity_db_unreadable": (
        "La base des scripts connus n'a pas pu être lue ({reason}) : aucun bloc n'a été "
        "confronté à elle. Tout le reste de ce rapport a été produit normalement."
    ),
    "identity_db_schema": (
        "La base des scripts connus est dans une forme que cette version ne connaît pas "
        "({found}) : aucun bloc n'a été confronté à elle. Tout le reste de ce rapport a "
        "été produit normalement."
    ),
    "identity_bad_entry": "Entrée #{index} de la base des scripts connus ignorée : {reason}",
    # -- headline summary --------------------------------------------------
    "summary_blocks_found": "{count} bloc(s) de code trouvé(s).",
    "summary_look_at_this": "<-- à regarder en priorité",
    "summary_and_hidden": "et cache une partie de ce qu'il fait",
    "summary_line": "  {count}x  {description} {marker}",
    # -- errors ------------------------------------------------------------
    "err_malformed": (
        "Ce fichier semble malformé ou hostile, donc Blend X-Ray a arrêté de le lire. Raison : {reason}"
    ),
    "err_not_blend": "Ce n'est pas un fichier Blender : {reason}",
    "err_unreadable": "Impossible de lire {path} : {reason}",
    "err_bat_version": (
        "Blend X-Ray nécessite blender-asset-tracer 1.23, mais la version {found} "
        "est installée.\n"
        "Les versions 2.x ont supprimé l'analyse autonome et nécessitent une "
        "installation de Blender 5.1+, ce qui irait à l'encontre du principe "
        "même de cet outil (inspecter un fichier SANS ouvrir Blender).\n"
        "Corrigez avec :  pip install -r requirements.txt"
    ),
    "err_bat_missing": (
        "blender-asset-tracer n'est pas installé. Blend X-Ray ne peut pas analyser "
        "les fichiers .blend sans lui.\n"
        "Corrigez avec :  pip install -r requirements.txt"
    ),
    "err_tool": "Blend X-Ray a rencontré une erreur interne : {reason}",
    # -- file header -------------------------------------------------------
    "compression_none": "non compressé",
    "compression_gzip": "compressé en gzip",
    "compression_zstd": "compressé en Zstandard",
    "compression_unrecognised": "compression non reconnue",
    "file_meta": (
        "Fichier Blender version {version}, pointeurs de {pointers} octets, "
        "{compression}, {blocks} blocs."
    ),
    "warnings_header": "Avertissements",
    # -- graphical interface -----------------------------------------------
    "gui_drop_prompt": "Déposez un fichier .blend ici, ou utilisez les boutons ci-dessous.",
    "gui_drop_unavailable": (
        "Le glisser-déposer n'est pas disponible dans cette version (le paquet "
        "optionnel tkinterdnd2 est absent). Utilisez les boutons ci-dessous à la "
        "place -- tout le reste fonctionne."
    ),
    "gui_choose_file": "Choisir un fichier...",
    "gui_choose_folder": "Choisir un dossier...",
    "gui_file_dialog_title": "Choisir un fichier .blend",
    "gui_folder_dialog_title": "Choisir un dossier où chercher des fichiers .blend",
    "gui_blend_filter": "Fichiers Blender",
    "gui_all_files": "Tous les fichiers",
    "gui_cancel": "Annuler",
    "gui_cancel_pending": "Arrêt après le fichier en cours de lecture...",
    "gui_copy_report": "Copier le rapport",
    "gui_copied": "Le rapport a été copié dans le presse-papiers, en texte brut.",
    "gui_copy_nothing": "Il n'y a pas encore de rapport à copier.",
    "gui_language": "Langue :",
    "gui_status_idle": (
        "Rien de chargé. Choisissez un fichier .blend ou un dossier pour commencer."
    ),
    "gui_status_reading": "Lecture : {path}",
    "gui_status_counted": "{done} fichier(s) lu(s) sur {total}.",
    "gui_status_done": "Lecture terminée : {total} fichier(s).",
    "gui_status_cancelled": (
        "Arrêté à votre demande après {done} fichier(s) sur {total}. Ce qui est "
        "affiché ci-dessous ne couvre que les fichiers déjà lus."
    ),
    "gui_status_no_files": "Aucun fichier .blend trouvé dans : {target}",
    "gui_source_show": "Afficher le code source ({lines} lignes)",
    "gui_source_hide": "Masquer le code source",
    "gui_source_hint": (
        "Le code source est affiché en dernier volontairement : c'est ce qui est "
        "le moins utile à l'écran pour une personne qui n'écrit pas de Python."
    ),
    "gui_source_capped": (
        "Ce bloc dépassait la limite de lecture par fichier, donc seule sa première "
        "partie a été lue. Ce qui est affiché ci-dessous est incomplet."
    ),
    "gui_error_header": "Ce fichier n'a pas pu être lu",
    "gui_draw_failed": "Ce résultat n'a pas pu être affiché : {reason}",
    # -- entrée du menu contextuel Windows (optionnelle, jamais une install) --
    "gui_shell_add": "Ajouter au menu clic droit",
    "gui_shell_remove": "Retirer du menu clic droit",
    "gui_shell_repair": "Réparer le menu clic droit",
    "gui_shell_stale": (
        "Une entrée existe déjà, mais elle lance une copie de Blend X-Ray qui ne "
        "se trouve plus à cet endroit : l'élément de menu ne fait donc rien pour "
        "l'instant. Voici ce qu'elle pointe aujourd'hui :\n{command}\n\nConfirmer "
        "la remplacera par la commande ci-dessous."
    ),
    "gui_shell_verb": "Inspecter avec {tool}",
    "gui_shell_dialog_title": "Modification du registre Windows",
    "gui_shell_explain": (
        "Cet outil vous demande de ne pas exécuter du code que vous n'avez pas "
        "regardé. Il s'applique la même règle : rien n'est écrit dans le registre "
        "tant que vous n'avez pas lu exactement ce qui va être écrit."
    ),
    "gui_shell_confirm_add": (
        "Ceci crée une clé de registre sous votre compte utilisateur uniquement "
        "(HKEY_CURRENT_USER). Aucun droit administrateur n'est nécessaire, rien "
        "ne change pour les autres comptes de cette machine, et le bouton "
        "« Retirer » annule l'opération.\n\n"
        "Clé :\n{key}\n\nValeur de la sous-clé \\command :\n{command}\n\nLa créer ?"
    ),
    "gui_shell_confirm_remove": (
        "Ceci supprime la clé de registre suivante, et rien d'autre.\n\n"
        "Clé :\n{key}\n\nLa supprimer ?"
    ),
    "gui_shell_added": (
        "Ajouté. Faites un clic droit sur un fichier .blend et choisissez « {label} »."
    ),
    "gui_shell_removed": "Retiré. L'entrée du menu contextuel a disparu.",
    "gui_shell_failed": "Le registre n'a pas pu être modifié : {reason}",
    # -- guard messages ----------------------------------------------------
    "guard_not_a_file": (
        "aucun fichier lisible à ce chemin -- il est absent, n'est pas un fichier, "
        "ou n'a pas pu être lu"
    ),
    "guard_short_file": "le fichier ne fait que {size} octets, trop petit pour être un fichier .blend",
    "guard_bad_magic": "il ne commence pas par les octets magiques BLENDER",
    "guard_bad_pointer_size": "l'en-tête déclare une taille de pointeur invalide ({char!r})",
    "guard_bad_endian": "l'en-tête déclare un ordre des octets invalide ({char!r})",
    "guard_bad_header_size": "l'en-tête déclare une taille d'en-tête inconnue ({size})",
    "guard_bad_format_version": (
        "l'en-tête déclare une version de format de fichier non prise en charge ({value!r})"
    ),
    "guard_bad_version": "l'en-tête déclare une version de Blender non numérique ({chars!r})",
    "guard_block_overruns": (
        "un bloc à la position {offset} déclare une longueur de {declared} "
        "octets, mais il ne reste que {remaining} octets dans le fichier"
    ),
    "guard_block_negative": "un bloc à la position {offset} déclare une longueur négative ({declared})",
    "guard_truncated": "le fichier s'arrête au milieu d'un en-tête de bloc, à la position {offset}",
    "guard_no_endb": "le fichier n'a pas de bloc ENDB, donc il est tronqué ou incomplet",
    "guard_too_many_blocks": "le fichier déclare plus de {limit} blocs",
    "guard_decompress_bomb": (
        "la décompression de ce fichier a produit plus de {limit} octets, ce qui "
        "correspond au profil d'une bombe de décompression"
    ),
    "guard_decompress_failed": "les données compressées n'ont pas pu être décompressées : {reason}",
    "guard_file_too_large": "le fichier fait {size} octets, au-dessus de la limite de {limit} octets",
    "guard_timeout": "la lecture de ce fichier a pris plus de {limit} secondes",
    "guard_path_too_long": (
        "un datablock déclare un chemin de fichier de {declared} octets, au-delà de "
        "la limite de {limit} octets -- aucun système de fichiers ne contient un "
        "chemin aussi long, donc ce champ n'en est pas un"
    ),
    "guard_string_too_long": (
        "un champ de type chaîne déclare {declared} octets, mais il ne reste "
        "que {remaining} octets dans le fichier"
    ),
}
