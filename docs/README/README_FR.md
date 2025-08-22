<div align="center">
  
  <img src="docs/images/logo.png" width="400" alt="QueryGPT">
  
  <br/>
  
  <p>
    <a href="README.md">English</a> •
    <a href="docs/README_CN.md">简体中文</a> •
    <a href="#">Français</a>
  </p>
  
  <br/>
  
  [![License](https://img.shields.io/badge/License-MIT-yellow.svg?style=for-the-badge)](LICENSE)
  [![Python](https://img.shields.io/badge/Python-3.10+-blue.svg?style=for-the-badge&logo=python&logoColor=white)](https://www.python.org/)
  [![OpenInterpreter](https://img.shields.io/badge/OpenInterpreter-0.4.3-green.svg?style=for-the-badge)](https://github.com/OpenInterpreter/open-interpreter)
  [![Stars](https://img.shields.io/github/stars/MoonMao42/ReceiptBI?style=for-the-badge&color=yellow)](https://github.com/MoonMao42/ReceiptBI/stargazers)
  
  <br/>
  
  <h3>Un Agent d'analyse de données intelligent basé sur OpenInterpreter</h3>
  <p><i>Dialoguez avec votre base de données en langage naturel</i></p>
  
</div>

<br/>

---

## ✨ Description du projet

QueryGPT est un système intelligent de requête et d'analyse de données qui révolutionne la façon dont vous interagissez avec vos bases de données. Utilisant la puissance de l'IA et d'OpenInterpreter, il transforme vos questions en langage naturel en analyses complexes, visualisations interactives et insights profonds.

**Pensez comme un analyste de données** - Notre Agent IA ne se contente pas d'exécuter des requêtes SQL simples. Il explore de manière autonome vos données, valide les résultats, effectue des analyses statistiques avancées et génère automatiquement des visualisations pertinentes.

## 🌟 Fonctionnalités principales

### 🤖 Capacités de l'Agent IA
- **Exploration autonome des données** : L'Agent examine proactivement les structures de tables et les échantillons de données
- **Validation multi-tours** : Vérifie et revalide les résultats pour garantir leur exactitude
- **Raisonnement transparent** : Affichage en temps réel du processus de réflexion de l'IA (Chain-of-Thought)
- **Mémoire contextuelle** : Comprend l'historique des conversations pour une analyse continue

### 📊 Analyse de données avancée
- **SQL + Python** : Exécution de code Python complexe pour l'analyse statistique et le machine learning
- **Visualisation intelligente** : Sélection automatique du meilleur type de graphique selon les données
- **Analyse statistique** : Corrélations, prédictions de tendances, détection d'anomalies
- **Export flexible** : Support des formats Excel, PDF, HTML et plus

### 🌍 Support multilingue
- **10 langues supportées** : Français, Anglais, Chinois, Espagnol, Portugais, Russe, Coréen, Allemand et plus
- **Conversion langage naturel vers SQL** : Posez vos questions dans votre langue maternelle
- **Compréhension des termes métiers** : Reconnaissance native des concepts commerciaux

### 🔒 Sécurité et déploiement
- **Sécurité des données** : Permissions en lecture seule, protection contre l'injection SQL
- **Déploiement flexible** : Cloud ou local avec Ollama, vos données restent privées
- **Multi-modèles** : Support de GPT-5, Claude, Gemini et modèles locaux Ollama

## 🛠 Stack technique

- **Backend** : Python 3.10+ avec Flask
- **Moteur d'analyse** : OpenInterpreter 0.4.3
- **Base de données** : MySQL ou compatible
- **Frontend** : HTML5, CSS3, JavaScript moderne
- **Visualisation** : Plotly, Chart.js
- **IA/LLM** : OpenAI API, Claude, Gemini, Ollama

## 📸 Captures d'écran du Système

<table>
  <tr>
    <td width="50%">
      <strong>🤖 Processus de Pensée de l'Agent Intelligent</strong><br/>
      <img src="docs/images/agent-thinking-en.png" width="100%" alt="Interface QueryGPT"/>
      <p align="center">Visualisation transparente de la chaîne de pensée</p>
    </td>
    <td width="50%">
      <strong>📊 Visualisation des Données</strong><br/>
      <img src="docs/images/data-visualization-en.png" width="100%" alt="Visualisation des Données"/>
      <p align="center">Génération intelligente de graphiques avec sélection automatique</p>
    </td>
  </tr>
  <tr>
    <td width="50%">
      <strong>👨‍💻 Vue Développeur</strong><br/>
      <img src="docs/images/developer-view-en.png" width="100%" alt="Vue Développeur"/>
      <p align="center">Détails d'exécution complets, SQL et code transparents</p>
    </td>
    <td width="50%">
      <strong>🌐 Support Multilingue</strong><br/>
      <img src="docs/images/main-interface.png" width="100%" alt="Interface Principale"/>
      <p align="center">Support de 10 langues, accessible mondialement</p>
    </td>
  </tr>
</table>

## 🚀 Démarrage rapide

### Installation initiale

```bash
# 1. Cloner le projet
git clone https://github.com/MoonMao42/ReceiptBI.git
cd QueryGPT

# 2. Exécuter le script de configuration (configure automatiquement l'environnement)
./setup.sh

# 3. Démarrer le service
./start.sh
```

### Utilisation ultérieure

```bash
# Démarrage rapide direct
./quick_start.sh
```

Le service s'exécute par défaut sur http://localhost:5000

> **Note** : Si le port 5000 est occupé, le système sélectionnera automatiquement le prochain port disponible (5001-5010).

## 💻 Utilisation

### Interface web

1. **Accédez à l'interface** : Ouvrez votre navigateur sur http://localhost:5000
2. **Posez vos questions** : Tapez vos requêtes en langage naturel
3. **Visualisez les résultats** : L'Agent génère automatiquement des graphiques et tableaux
4. **Explorez l'historique** : Retrouvez et partagez vos analyses précédentes

### Exemples de requêtes

- "Montre-moi les ventes du mois dernier"
- "Quelle est la répartition des ventes par catégorie de produit ?"
- "Identifie les 10 meilleurs clients par chiffre d'affaires"
- "Génère un graphique de tendance des ventes sur 6 mois"
- "Analyse la corrélation entre le prix et le volume des ventes"

### API REST

```http
POST /api/chat
Content-Type: application/json

{
  "message": "Votre requête en langage naturel",
  "model": "default",
  "stream": false
}
```

## ⚙️ Configuration requise

### Système
- **Python** : 3.10.x (Obligatoire pour OpenInterpreter 0.4.3)
- **Mémoire** : 4 GB RAM minimum
- **Stockage** : 2 GB d'espace libre
- **OS** : Linux, macOS, Windows

### Base de données
- MySQL 5.7+ ou MariaDB
- PostgreSQL 12+ (support partiel)
- Autres bases SQL compatibles

### Configuration

1. **Variables d'environnement** (.env)
   ```bash
   OPENAI_API_KEY=votre_clé_api
   OPENAI_BASE_URL=https://api.openai.com/v1
   DB_HOST=localhost
   DB_USER=utilisateur
   DB_PASSWORD=motdepasse
   DB_NAME=nom_base
   ```

2. **Configuration des modèles** (config/models.json)
   ```json
   {
     "models": [
       {
         "name": "GPT-4",
         "id": "gpt-4",
         "api_base": "https://api.openai.com/v1"
       }
     ]
   }
   ```

## 📊 Comparaison avec d'autres solutions

| Fonctionnalité | **QueryGPT** | Vanna AI | DB-GPT | TableGPT | Text2SQL.AI |
|----------------|:------------:|:--------:|:------:|:--------:|:-----------:|
| **Gratuit et Open Source** | ✅ | Partial | ✅ | ❌ | ❌ |
| **Support multilingue (10 langues)** | ✅ | ❌ | Partial | Partial | ❌ |
| **Exécution Python complète** | ✅ | ❌ | ❌ | ❌ | ❌ |
| **Visualisation pilotée par IA** | ✅ | Basique | ✅ | ✅ | Basique |
| **Exploration autonome** | ✅ | ❌ | Partial | Partial | ❌ |
| **Processus de pensée visible** | ✅ | ❌ | ❌ | ❌ | ❌ |
| **Déploiement local** | ✅ | ✅ | ✅ | ❌ | ❌ |

### Nos différenciateurs clés

- **Environnement Python complet** : Pas de limitations, exécutez n'importe quel code d'analyse
- **Transparence totale** : Voyez exactement ce que l'IA pense et fait
- **Extensibilité illimitée** : Installez de nouvelles bibliothèques selon vos besoins
- **Vraiment gratuit** : Licence MIT, aucun paywall caché

## 🤝 Contribution

Les contributions sont les bienvenues ! N'hésitez pas à :

1. Forker le projet
2. Créer votre branche de fonctionnalité (`git checkout -b feature/NouvelleFonctionnalite`)
3. Committer vos changements (`git commit -m 'Ajout d'une fonctionnalité'`)
4. Pousser vers la branche (`git push origin feature/NouvelleFonctionnalite`)
5. Ouvrir une Pull Request

## 📄 Licence

Ce projet est sous licence MIT - voir le fichier [LICENSE](LICENSE) pour plus de détails.

## 👨‍💻 Auteur

- **Auteur** : MoonMao42
- **GitHub** : [@MoonMao42](https://github.com/MoonMao42)
- **Créé** : Août 2025

## 🌟 Support

Si vous trouvez ce projet utile, n'hésitez pas à :
- ⭐ Mettre une étoile sur GitHub
- 🐛 Signaler des bugs ou suggérer des améliorations
- 📖 Contribuer à la documentation
- 💬 Partager avec votre communauté

## 📚 Documentation supplémentaire

- [Documentation API](docs/API.md)
- [Guide de configuration](docs/CONFIGURATION.md)
- [Guide de déploiement](docs/DEPLOYMENT.md)
- [Configuration de la couche sémantique](backend/SEMANTIC_LAYER_SETUP.md)

---

<div align="center">
  <b>QueryGPT - L'intelligence artificielle au service de vos données</b>
  <br/>
  <i>Transformez vos questions en insights</i>
</div>