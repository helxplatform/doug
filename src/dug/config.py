import os

from dataclasses import dataclass, field


TRANQL_SOURCE: str = "redis:test"


@dataclass
class Config:
    """
        TODO: Populate description
    """
    elastic_password: str = "changeme"
    redis_password: str = "changeme"

    elastic_host: str = "elasticsearch"
    elastic_port: int = 9200
    elastic_username: str = "elastic"

    redis_host: str = "redis"
    redis_port: int = 6379

    nboost_host: str = "nboost"
    nboost_port: int = 8000

    # Preprocessor config that will be passed to annotate.Preprocessor constructor
    preprocessor: dict = field(default_factory=lambda: {
        "debreviator": {
            "BMI": "body mass index"
        },
        "stopwords": ["the"]
    })

    # Annotator config that will be passed to annotate.Annotator constructor
    annotator: dict = field(default_factory=lambda: {
        "url": "https://api.monarchinitiative.org/api/nlp/annotate/entities?min_length=4&longest_only=false&include_abbreviation=false&include_acronym=false&include_numbers=false&content="
    })

    # Normalizer config that will be passed to annotate.Normalizer constructor
    normalizer: dict = field(default_factory=lambda: {
        "url": "https://nodenormalization-dev.apps.renci.org/get_normalized_nodes?conflate=false&description=true&curie="
    })

    # Synonym service config that will be passed to annotate.SynonymHelper constructor
    synonym_service: dict = field(default_factory=lambda: {
        "url": "https://name-resolution-sri.renci.org/reverse_lookup"
    })

    # Ontology metadata helper config that will be passed to annotate.OntologyHelper constructor
    ontology_helper: dict = field(default_factory=lambda: {
        "url": "https://api.monarchinitiative.org/api/bioentity/"
    })

    # Redlist of identifiers not to expand via TranQL
    tranql_exclude_identifiers: list = field(default_factory=lambda: ["CHEBI:17336"])

    tranql_queries: dict = field(default_factory=lambda: {
        "disease": ["disease", "phenotypic_feature"],
        "pheno": ["phenotypic_feature", "disease"],
        "anat": ["disease", "anatomical_entity"],
        "chem_to_disease": ["chemical_entity", "disease"],
        "small_molecule_to_disease": ["small_molecule", "disease"],
        "chemical_mixture_to_disease": ["chemical_mixture", "disease"],
        "phen_to_anat": ["phenotypic_feature", "anatomical_entity"],
    })

    node_to_element_queries: dict = field(default_factory=lambda: {
        # Dug element type to cast the query kg nodes to
        "cde": {
            # Parse nodes matching criteria in kg
            "node_type": "biolink:Publication",
            "curie_prefix": "HEALCDE",
            "array_to_string": [
                "files"
            ]
            "attribute_mapping": {
                # "DugElement Attribute" : "KG Node attribute"
                "name": "name",
                "desc": "summary",
                "collection_name": "cde_category",
                "collection_id":  "cde_category",
                "collection_action": "files"
            }
        }
    })

    concept_expander: dict = field(default_factory=lambda: {
        "url": "https://tranql-dev.renci.org/tranql/query?dynamic_id_resolution=true&asynchronous=false",
        "min_tranql_score": 0.0
    })

    # List of ontology types that can be used even if they fail normalization
    ontology_greenlist: list = field(default_factory=lambda: ["PATO", "CHEBI", "MONDO", "UBERON", "HP", "MESH", "UMLS"])

    @classmethod
    def from_env(cls):
        env_vars = {
            "elastic_host": "ELASTIC_API_HOST",
            "elastic_port": "ELASTIC_API_PORT",
            "elastic_username": "ELASTIC_USERNAME",
            "elastic_password": "ELASTIC_PASSWORD",
            "redis_host": "REDIS_HOST",
            "redis_port": "REDIS_PORT",
            "redis_password": "REDIS_PASSWORD"
        }

        kwargs = {}

        for kwarg, env_var in env_vars.items():
            env_value = os.environ.get(env_var)
            if env_value:
                kwargs[kwarg] = env_value
        return cls(**kwargs)
