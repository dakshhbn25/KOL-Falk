"""Run one source:  python main.py pubmed | clinicaltrials | sasl"""
import argparse
import logging

from connectors.clinicaltrials_connector import ClinicalTrialsConnector
from connectors.pubmed_connector import PubMedConnector
from connectors.sasl_connector import SaslConnector
from core import settings

CONNECTORS = {
    "pubmed": PubMedConnector,
    "clinicaltrials": ClinicalTrialsConnector,
    "sasl": SaslConnector,
}

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    parser = argparse.ArgumentParser()
    parser.add_argument("source", choices=CONNECTORS)
    parser.add_argument("--project", default="dr_falk_swiss_psc")
    args = parser.parse_args()
    project = settings.load_project(args.project)
    print("saved:", CONNECTORS[args.source](project).run())
