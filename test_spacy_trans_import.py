try:
    from spacy_transformers.pipeline_component import TransformersModel
    print("Import OK")
except Exception as e:
    import traceback
    traceback.print_exc()
