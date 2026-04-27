# StageCheck — OSINT & Detection of Fraudulent Internship Offers

---

#  English Version

##  Overview

StageCheck is an **OSINT (Open Source Intelligence)** and **Cyber Threat Intelligence (CTI)** platform designed to detect fraudulent or low-credibility internship and job offers.

It collects job postings from recruitment platforms, enriches them using external intelligence sources, and assigns a **credibility score using AI and CTI analysis**.

The goal is to protect students and young professionals from scams, phishing, and fake internship offers.

---

##  Objectives

- Automatically collect internship/job offers from major platforms
- Enrich data using OSINT & CTI sources
- Detect fraudulent or suspicious offers
- Provide a **real-time credibility scoring system**
- Ensure a modular and scalable architecture

---

##  Target Platforms

- Welcome to the Jungle
- Stage.fr
- JobTeaser

The system is extensible and supports adding new data sources.

---

##  Problem Statement

How can we build a scalable and automated system capable of detecting fraudulent internship offers using:

- OSINT (Open Source Intelligence)
- CTI (Cyber Threat Intelligence)
- AI (LLMs via Ollama)

while maintaining accuracy and performance?

---

##  Risks Addressed

- Personal data harvesting
- Fake recruitment fees
- Phishing and social engineering attacks
- Time loss for candidates
- Reputation damage for platforms

---

##  Architecture

The system includes:

- Web scraping modules
- OSINT enrichment pipeline
- CTI integration (MISP + APIs)
- AI analysis layer (Ollama)
- MongoDB database
- Dockerized deployment

---
## 1. Install MISP (CTI Platform)

Use the containerized version of MISP:

## 2. Environment Variables
---
Create a `.env` file inside `publicscrapper/`:
```env
MONGO_URI=""
VIRUSTOTAL_API_KEY=""
ABUSEIPDB_API_KEY=""
SHODAN_API_KEY=""
MISP_URL=""
MISP_API_KEY=""
OLLAMA_URL=""
```
---
## 3. Start the containers 
docker compose up
#  StageCheck — OSINT & Détection des Offres de Stage Frauduleuses

---

#  Version Française

##  Vue d’ensemble

StageCheck est une plateforme d’**OSINT (Open Source Intelligence)** et de **Cyber Threat Intelligence (CTI)** conçue pour détecter les offres de stage et d’emploi frauduleuses ou de faible crédibilité.

Elle collecte des offres d’emploi depuis des plateformes de recrutement, les enrichit via des sources d’intelligence externes, puis attribue un **score de crédibilité basé sur l’IA et l’analyse CTI**.

L’objectif est de protéger les étudiants et jeunes professionnels contre les arnaques, le phishing et les fausses offres de stage.

---

##  Objectifs

- Collecter automatiquement des offres de stage / emploi depuis les principales plateformes
- Enrichir les données via des sources OSINT et CTI
- Détecter les offres frauduleuses ou suspectes
- Fournir un **système de scoring de crédibilité en temps réel**
- Garantir une architecture modulaire et scalable

---

##  Plateformes ciblées

- Welcome to the Jungle  
- Stage.fr  
- JobTeaser  

Le système est extensible et permet d’ajouter facilement de nouvelles sources de données.

---

##  Problématique

Comment construire un système automatisé et scalable capable de détecter les offres de stage frauduleuses en utilisant :

- l’OSINT (Open Source Intelligence)
- le CTI (Cyber Threat Intelligence)
- l’IA (LLMs via Ollama)

tout en garantissant précision et performance ?

---

##  Risques traités

- Vol de données personnelles  
- Faux frais de recrutement  
- Phishing et attaques d’ingénierie sociale  
- Perte de temps pour les candidats  
- Atteinte à la réputation des plateformes  

---

##  Architecture

Le système inclut :

- Modules de scraping web  
- Pipeline d’enrichissement OSINT  
- Intégration CTI (MISP + APIs)  
- Couche d’analyse IA (Ollama)  
- Base de données MongoDB  
- Déploiement via Docker  

---

##  Installation

### 1. Installation de MISP (plateforme CTI)

Utiliser la version conteneurisée de MISP.

---

### 2. Variables d’environnement

Créer un fichier `.env` dans `publicscrapper/` :

```env
MONGO_URI=""
VIRUSTOTAL_API_KEY=""
ABUSEIPDB_API_KEY=""
SHODAN_API_KEY=""
MISP_URL=""
MISP_API_KEY=""
OLLAMA_URL=""
```
---
### 3. Démarrage des conteneurs
docker compose up
