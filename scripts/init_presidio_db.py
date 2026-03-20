import sys
import os
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

# Add project root to path
sys.path.append(os.getcwd())

from app.db.session import engine
from app.models.presidio_engine import PresidioEngine

def init_db():
    print("Initializing database tables...")
    try:
        # Create tables
        PresidioEngine.metadata.create_all(bind=engine)
        print("Successfully ensured presidio_engines table exists.")
        
        # Seed data
        with Session(engine) as session:
            count = session.query(PresidioEngine).count()
            if count == 0:
                print("Seeding default engines...")
                spacy = PresidioEngine(
                    name="spaCy (en_core_web_lg)",
                    engine_type="spacy",
                    model_name="en_core_web_lg",
                    is_active=False,
                    description="Standard spaCy model (fast, decent accuracy)"
                )
                transformers = PresidioEngine(
                    name="Transformer (RoBERTa i2b2)",
                    engine_type="transformers",
                    model_name="obi/deid_roberta_i2b2",
                    is_active=False,
                    description="RoBERTa-based model trained on i2b2 dataset"
                )
                theekshana = PresidioEngine(
                    name="Theekshana Medical NER",
                    engine_type="transformers",
                    model_name="theekshana/deid-roberta-i2b2-NER-medical-reports",
                    is_active=False,
                    description="Advanced medical NER model from HuggingFace (optimized for medical reports)"
                )
                stanford = PresidioEngine(
                    name="Stanford De-identifier",
                    engine_type="transformers",
                    model_name="StanfordAIMI/stanford-deidentifier-base",
                    is_active=True,
                    description="PubMedBERT-based medical de-identifier from Stanford AIMI (default)"
                )
                trf = PresidioEngine(
                    name="spaCy Transformer (trf)",
                    engine_type="spacy",
                    model_name="en_core_web_trf",
                    is_active=False,
                    description="High-accuracy spaCy transformer model (RobertA-base)"
                )
                session.add_all([spacy, transformers, theekshana, stanford, trf])
                session.commit()
                print("Seeded default engines.")
            else:
                print(f"Found {count} existing engines.")
                
    except Exception as e:
        print(f"Error initializing DB: {e}")

if __name__ == "__main__":
    init_db()
