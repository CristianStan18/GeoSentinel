# GeoSentinel

GeoSentinel is an early-warning intelligence platform designed to monitor, detect, and analyze signals related to critical infrastructure and environmental risk. The system integrates data ingestion pipelines, detection logic, and a web-based visualization layer to support situational awareness and operational decision-making.

## Overview

GeoSentinel ingests real and synthetic geospatial and environmental data, applies detection logic to identify anomalies or emerging risks, and presents results through an interactive dashboard. The platform is modular and extensible, supporting both automated analysis and analyst-driven operational briefings.

## Project Structure

- ingestion/ — Data ingestion pipelines and preprocessing  
- detection/ — Detection and alerting logic  
- api/ — Backend API and dashboard server  
- dashboard/ — Web-based visualization components  
- agent/ — Operational briefing and agent workflows  
- data/ — Sample or processed datasets  
- prompts/ — Prompt templates for agent execution  

## Requirements

- Python 3.10 or newer  
- Dependencies listed in requirements.txt  

## Installation and Usage

1. Clone the repository:
   ```bash
   git clone https://github.com/CristianStan18/GeoSentinel.git
   cd GeoSentinel
   ```

2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

3. Run ingestion and detection:
   ```bash
   python -m ingestion.real_data
   python -m detection.detect
   ```

4. Start the dashboard server:
   ```bash
   python -m api.server
   ```
   Access the dashboard at http://localhost:5000.

## Capabilities

- Environmental and geospatial data ingestion  
- Anomaly and risk detection logic  
- Interactive dashboard visualization  
- Offline and LLM-assisted operational briefings  

## Disclaimer

GeoSentinel is a decision-support and analytical tool. Outputs should not be considered definitive assessments and should be validated by domain experts and official sources.

## License

No license is currently specified. Consider adding a license file to define usage and distribution terms.
