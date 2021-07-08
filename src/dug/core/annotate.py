import json
import logging
import os
import urllib.parse
from typing import TypeVar, Generic, Union, List, Tuple

import requests
from requests import Session

import dug.core.tranql as tql

logger = logging.getLogger('dug')

logging.getLogger("requests").setLevel(logging.WARNING)
logging.getLogger("urllib3").setLevel(logging.WARNING)


class Identifier:
    def __init__(self, id, label, types=None, search_text="", description=""):
        self.id = id
        self.label = label
        self.description = description
        if types is None:
            types = []
        self.types = types
        self.search_text = [search_text] if search_text else []
        self.equivalent_identifiers = []
        self.synonyms = []
        self.purl = ""

    @property
    def id_type(self):
        return self.id.split(":")[0]

    def add_search_text(self, text):
        # Add text only if it's unique and if not empty string
        if text and text not in self.search_text:
            self.search_text.append(text)

    def get_searchable_dict(self):
        # Return a version of the identifier compatible with what's in ElasticSearch
        es_ident = {
            'id': self.id,
            'label': self.label,
            'equivalent_identifiers': self.equivalent_identifiers,
            'type': self.types,
            'synonyms': self.synonyms
        }
        return es_ident

    def jsonable(self):
        return self.__dict__


class DugAnnotator:
    def __init__(
            self,
            preprocessor: "Preprocessor",
            annotator: "Annotator",
            normalizer: "Normalizer",
            synonym_finder: "SynonymFinder",
            ontology_helper: "OntologyHelper",
            ontology_greenlist=[],
    ):
        self.preprocessor = preprocessor
        self.annotator = annotator
        self.normalizer = normalizer
        self.synonym_finder = synonym_finder
        self.ontology_helper = ontology_helper
        self.ontology_greenlist = ontology_greenlist
        self.norm_fails_file = "norm_fails.txt"
        self.anno_fails_file = "anno_fails.txt"

    def annotate(self, text, http_session):

        # Preprocess text (debraviate, remove stopwords, etc.)
        text = self.preprocessor.preprocess(text)

        # Fetch identifiers
        raw_identifiers = self.annotator.annotate(text, http_session)

        # Write out to file if text fails to annotate
        if not raw_identifiers:
            with open(self.anno_fails_file, "a") as fh:
                fh.write(f'{text}\n')

        processed_identifiers = []
        for identifier in raw_identifiers:

            # Normalize identifier using normalization service
            norm_id = self.normalizer.normalize(identifier, http_session)

            # Skip adding id if it doesn't normalize
            if norm_id is None:
                # Write out to file if identifier doesn't normalize
                with open(self.norm_fails_file, "a") as fh:
                    fh.write(f'{identifier.id}\n')

                # Discard non-normalized ident if not in greenlist
                if identifier.id_type not in self.ontology_greenlist:
                    continue

                # If it is in greenlist just keep moving forward
                norm_id = identifier

            # Add synonyms to identifier
            norm_id.synonyms = self.synonym_finder.get_synonyms(norm_id.id, http_session)

            # Get canonical label, name, and description from ontology metadata service
            name, desc, ontology_type = self.ontology_helper.get_ontology_info(norm_id.id, http_session)
            norm_id.label = name
            norm_id.description = desc
            norm_id.type = ontology_type

            # Get pURL for ontology identifer for more info
            norm_id.purl = BioLinkPURLerizer.get_curie_purl(norm_id.id)
            processed_identifiers.append(norm_id)

        return processed_identifiers


class ConceptExpander:
    def __init__(self, url, min_tranql_score=0.2):
        self.url = url
        self.min_tranql_score = min_tranql_score
        self.include_node_keys = ["id", "name", "synonyms"]
        self.include_edge_keys = []
        self.tranql_headers = {"accept": "application/json", "Content-Type": "text/plain"}

    def is_acceptable_answer(self, answer):
        return True

    def expand_identifier(self, identifier, query_factory, kg_filename):

        answer_kgs = []

        # Skip TranQL query if a file exists in the crawlspace exists already, but continue w/ answers
        if os.path.exists(kg_filename):
            logger.info(f"identifier {identifier} is already crawled. Skipping TranQL query.")
            with open(kg_filename, 'r') as stream:
                response = json.load(stream)
        else:
            query = query_factory.get_query(identifier)
            logger.debug(query)
            response = requests.post(
                url=self.url,
                headers=self.tranql_headers,
                data=query).json()

            # Case: Skip if empty KG
            logger.debug(response)
            if 'knowledge_graph' not in response:
                logger.debug(f"Did not find a knowledge graph for {query}")
                return []
            if not len(response['knowledge_graph']['nodes']):
                logger.debug(f"Did not find a knowledge graph for {query}")
                return []

            # Dump out to file if there's a knowledge graph
            with open(kg_filename, 'w') as stream:
                json.dump(response, stream, indent=2)

        # Get nodes in knowledge graph hashed by ids for easy lookup
        kg = tql.QueryKG(response)

        for answer in kg.answers:
            # Filter out answers that don't meet some criteria
            # Right now just don't filter anything
            logger.debug(f"Answer: {answer}")
            if not self.is_acceptable_answer(answer):
                logger.warning("Skipping answer as it failed one or more acceptance criteria. See log for details.")
                continue

            # Get subgraph containing only information for this answer
            try:
                # Temporarily surround in try/except because sometimes the answer graphs
                # contain invalid references to edges/nodes
                # This will be fixed in Robokop but for now just silently warn if answer is invalid
                answer_kg = kg.get_answer_subgraph(answer,
                                                   include_node_keys=self.include_node_keys,
                                                   include_edge_keys=self.include_edge_keys)

                # Add subgraph to list of acceptable answers to query
                answer_kgs.append(answer_kg)

            except tql.MissingNodeReferenceError:
                # TEMPORARY: Skip answers that have invalid node references
                # Need this to be fixed in Robokop
                logger.warning("Skipping answer due to presence of non-preferred id! "
                               "See err msg for details.")
                continue
            except tql.MissingEdgeReferenceError:
                # TEMPORARY: Skip answers that have invalid edge references
                # Need this to be fixed in Robokop
                logger.warning("Skipping answer due to presence of invalid edge reference! "
                               "See err msg for details.")
                continue

        return answer_kgs


class Preprocessor:
    """"Class for preprocessing strings so they are better interpreted by NLP steps"""

    def __init__(self, debreviator=None, stopwords=None):
        if debreviator is None:
            debreviator = self.default_debreviator_factory()
        self.decoder = debreviator

        if stopwords is None:
            stopwords = []
        self.stopwords = stopwords

    def preprocess(self, text: str) -> str:
        """
        Apply debreviator to replace abbreviations and other characters

        >>> pp = Preprocessor({"foo": "bar"}, ["baz"])
        >>> pp.preprocess("Hello foo")
        'Hello bar'

        >>> pp.preprocess("Hello baz world")
        'Hello world'
        """

        for key, value in self.decoder.items():
            text = text.replace(key, value)

        # Remove any stopwords
        text = " ".join([word for word in text.split() if word not in self.stopwords])
        return text

    @staticmethod
    def default_debreviator_factory():
        return {"bmi": "body mass index", "_": " "}


Input = TypeVar("Input")
Output = TypeVar("Output")


class ApiClient(Generic[Input, Output]):

    def make_request(self, value: Input, http_session: Session):
        raise NotImplementedError()

    def handle_response(self, value, response: Union[dict, list]) -> Output:
        raise NotImplementedError()

    def __call__(self, value: Input, http_session: Session) -> Output:
        response = self.make_request(value, http_session)

        result = self.handle_response(value, response)

        return result


class Annotator(ApiClient[str, List[Identifier]]):
    """
    Use monarch API service to fetch ontology IDs found in text
    """

    def __init__(self, url: str):
        self.url = url

    def annotate(self, text, http_session):
        logger.debug(f"Annotating: {text}")
        return self(text, http_session)

    def make_request(self, value: Input, http_session: Session):
        value = urllib.parse.quote(value)
        url = f'{self.url}{value}'

        return http_session.get(url).json()

    def handle_response(self, value, response: dict) -> List[Identifier]:
        identifiers = []
        """ Parse each identifier and initialize identifier object """
        for span in response.get('spans', []):
            search_text = span.get('text', None)
            for token in span.get('token', []):
                curie = token.get('id', None)
                if not curie:
                    continue

                biolink_types = token.get('category')
                label = token.get('terms')[0]
                identifiers.append(Identifier(id=curie,
                                              label=label,
                                              types=biolink_types,
                                              search_text=search_text))
        return identifiers


class Normalizer(ApiClient[Identifier, Identifier]):
    def __init__(self, url):
        self.url = url

    def normalize(self, identifier: Identifier, http_session: Session):
        # Use RENCI's normalization API service to get the preferred version of an identifier
        logger.debug(f"Normalizing: {identifier.id}")
        return self(identifier, http_session)

    def make_request(self, value: Identifier, http_session: Session) -> dict:
        curie = value.id
        url = f"{self.url}{urllib.parse.quote(curie)}"
        response = http_session.get(url)
        logger.debug(f"make_request^response: {len(response)} {response}")
        normalized = response.json() # normalized = http_session.get(url).json()
        return normalized

    def handle_response(self, identifier: Identifier, normalized: dict) -> Identifier:
        """ Record normalized results. """
        curie = identifier.id
        normalization = normalized.get(curie, {})
        if normalization is None:
            logger.error(f"Normalization service did not return normalization for: {curie}")
            return None

        preferred_id = normalization.get("id", {})
        equivalent_identifiers = normalization.get("equivalent_identifiers", [])
        biolink_type = normalization.get("type", [])

        # Return none if there isn't actually a preferred id
        if 'identifier' not in preferred_id:
            logger.debug(f"ERROR: normalize({curie})=>({preferred_id}). No identifier?")
            return None

        logger.debug(f"Preferred id: {preferred_id}")
        identifier.id = preferred_id.get('identifier', '')
        identifier.label = preferred_id.get('label', '')
        identifier.equivalent_identifiers = [v['identifier'] for v in equivalent_identifiers]
        identifier.types = biolink_type

        return identifier


class SynonymFinder(ApiClient[str, List[str]]):

    def __init__(self, url: str):
        self.url = url

    def get_synonyms(self, curie: str, http_session):
        '''
        This function uses the NCATS translator service to return a list of synonyms for
        curie id
        '''

        return self(curie, http_session)

    def make_request(self, curie: str, http_session: Session):

        # Get response from synonym service
        url = f"{self.url}{urllib.parse.quote(curie)}"

        try:
            response = http_session.get(url)
            if response.status_code == 400:
                logger.error(f"No synonyms returned for: `{curie}`. Validation error.")
                return []
            if response.status_code == 500:
                logger.error(f"No synonyms returned for: `{curie}`. Internal server error from {self.url}.")
                return []
            return response.json()
        except json.decoder.JSONDecodeError as e:
            logger.error(f"Json parse error for response from `{url}`. Exception: {str(e)}")
            return []

    def handle_response(self, curie: str, raw_synonyms: List[dict]) -> List[str]:
        # List comprehension unpack all synonyms into a list
        return [synonym['desc'] for synonym in raw_synonyms]


class OntologyHelper(ApiClient[str, Tuple[str, str, str]]):
    def __init__(self, url):
        self.url = url

    def make_request(self, curie: str, http_session: Session):
        url = f"{self.url}{urllib.parse.quote(curie)}"
        try:
            response = http_session.get(url).json()
            return response
        except json.decoder.JSONDecodeError as e:
            logger.error(f"No labels returned for: {curie}")
            return {}

    def handle_response(self, curie: str, response: dict) -> Tuple[str,str,str]:
        # List comprehension for synonyms
        name = response.get('label', '')
        description = '' if not response.get('description', None) else response.get('description', '')
        ontology_type = '' if not response.get('category', None) else response.get('category', '')[0]

        return name, description, ontology_type

    def get_ontology_info(self, curie, http_session):
        return self(curie, http_session)


class BioLinkPURLerizer:
    # Static class for the sole purpose of doing lookups of different ontology PURLs
    # Is it pretty? No. But it gets the job done.
    biolink_lookup = {"APO": "http://purl.obolibrary.org/obo/APO_",
                      "Aeolus": "http://translator.ncats.nih.gov/Aeolus_",
                      "BIOGRID": "http://identifiers.org/biogrid/",
                      "BIOSAMPLE": "http://identifiers.org/biosample/",
                      "BSPO": "http://purl.obolibrary.org/obo/BSPO_",
                      "CAID": "http://reg.clinicalgenome.org/redmine/projects/registry/genboree_registry/by_caid?caid=",
                      "CHEBI": "http://purl.obolibrary.org/obo/CHEBI_",
                      "CHEMBL.COMPOUND": "http://identifiers.org/chembl.compound/",
                      "CHEMBL.MECHANISM": "https://www.ebi.ac.uk/chembl/mechanism/inspect/",
                      "CHEMBL.TARGET": "http://identifiers.org/chembl.target/",
                      "CID": "http://pubchem.ncbi.nlm.nih.gov/compound/",
                      "CL": "http://purl.obolibrary.org/obo/CL_",
                      "CLINVAR": "http://identifiers.org/clinvar/",
                      "CLO": "http://purl.obolibrary.org/obo/CLO_",
                      "COAR_RESOURCE": "http://purl.org/coar/resource_type/",
                      "CPT": "https://www.ama-assn.org/practice-management/cpt/",
                      "CTD": "http://translator.ncats.nih.gov/CTD_",
                      "ClinVarVariant": "http://www.ncbi.nlm.nih.gov/clinvar/variation/",
                      "DBSNP": "http://identifiers.org/dbsnp/",
                      "DGIdb": "https://www.dgidb.org/interaction_types",
                      "DOID": "http://purl.obolibrary.org/obo/DOID_",
                      "DRUGBANK": "http://identifiers.org/drugbank/",
                      "DrugCentral": "http://translator.ncats.nih.gov/DrugCentral_",
                      "EC": "http://www.enzyme-database.org/query.php?ec=",
                      "ECTO": "http://purl.obolibrary.org/obo/ECTO_",
                      "EDAM-DATA": "http://edamontology.org/data_",
                      "EDAM-FORMAT": "http://edamontology.org/format_",
                      "EDAM-OPERATION": "http://edamontology.org/operation_",
                      "EDAM-TOPIC": "http://edamontology.org/topic_",
                      "EFO": "http://identifiers.org/efo/",
                      "ENSEMBL": "http://identifiers.org/ensembl/",
                      "ExO": "http://purl.obolibrary.org/obo/ExO_",
                      "FAO": "http://purl.obolibrary.org/obo/FAO_",
                      "FB": "http://identifiers.org/fb/",
                      "FBcv": "http://purl.obolibrary.org/obo/FBcv_",
                      "FlyBase": "http://flybase.org/reports/",
                      "GAMMA": "http://translator.renci.org/GAMMA_",
                      "GO": "http://purl.obolibrary.org/obo/GO_",
                      "GOLD.META": "http://identifiers.org/gold.meta/",
                      "GOP": "http://purl.obolibrary.org/obo/go#",
                      "GOREL": "http://purl.obolibrary.org/obo/GOREL_",
                      "GSID": "https://scholar.google.com/citations?user=",
                      "GTEx": "https://www.gtexportal.org/home/gene/",
                      "HANCESTRO": "http://www.ebi.ac.uk/ancestro/ancestro_",
                      "HCPCS": "http://purl.bioontology.org/ontology/HCPCS/",
                      "HGNC": "http://identifiers.org/hgnc/",
                      "HGNC.FAMILY": "http://identifiers.org/hgnc.family/",
                      "HMDB": "http://identifiers.org/hmdb/",
                      "HP": "http://purl.obolibrary.org/obo/HP_",
                      "ICD0": "http://translator.ncats.nih.gov/ICD0_",
                      "ICD10": "http://translator.ncats.nih.gov/ICD10_",
                      "ICD9": "http://translator.ncats.nih.gov/ICD9_",
                      "INCHI": "http://identifiers.org/inchi/",
                      "INCHIKEY": "http://identifiers.org/inchikey/",
                      "INTACT": "http://identifiers.org/intact/",
                      "IUPHAR.FAMILY": "http://identifiers.org/iuphar.family/",
                      "KEGG": "http://identifiers.org/kegg/",
                      "LOINC": "http://loinc.org/rdf/",
                      "MEDDRA": "http://identifiers.org/meddra/",
                      "MESH": "http://identifiers.org/mesh/",
                      "MGI": "http://identifiers.org/mgi/",
                      "MI": "http://purl.obolibrary.org/obo/MI_",
                      "MIR": "http://identifiers.org/mir/",
                      "MONDO": "http://purl.obolibrary.org/obo/MONDO_",
                      "MP": "http://purl.obolibrary.org/obo/MP_",
                      "MSigDB": "https://www.gsea-msigdb.org/gsea/msigdb/",
                      "MetaCyc": "http://translator.ncats.nih.gov/MetaCyc_",
                      "NCBIGENE": "http://identifiers.org/ncbigene/",
                      "NCBITaxon": "http://purl.obolibrary.org/obo/NCBITaxon_",
                      "NCIT": "http://purl.obolibrary.org/obo/NCIT_",
                      "NDDF": "http://purl.bioontology.org/ontology/NDDF/",
                      "NLMID": "https://www.ncbi.nlm.nih.gov/nlmcatalog/?term=",
                      "OBAN": "http://purl.org/oban/",
                      "OBOREL": "http://purl.obolibrary.org/obo/RO_",
                      "OIO": "http://www.geneontology.org/formats/oboInOwl#",
                      "OMIM": "http://purl.obolibrary.org/obo/OMIM_",
                      "ORCID": "https://orcid.org/",
                      "ORPHA": "http://www.orpha.net/ORDO/Orphanet_",
                      "ORPHANET": "http://identifiers.org/orphanet/",
                      "PANTHER.FAMILY": "http://identifiers.org/panther.family/",
                      "PANTHER.PATHWAY": "http://identifiers.org/panther.pathway/",
                      "PATO-PROPERTY": "http://purl.obolibrary.org/obo/pato#",
                      "PDQ": "https://www.cancer.gov/publications/pdq#",
                      "PHARMGKB.DRUG": "http://identifiers.org/pharmgkb.drug/",
                      "PHARMGKB.PATHWAYS": "http://identifiers.org/pharmgkb.pathways/",
                      "PHAROS": "http://pharos.nih.gov",
                      "PMID": "http://www.ncbi.nlm.nih.gov/pubmed/",
                      "PO": "http://purl.obolibrary.org/obo/PO_",
                      "POMBASE": "http://identifiers.org/pombase/",
                      "PR": "http://purl.obolibrary.org/obo/PR_",
                      "PUBCHEM.COMPOUND": "http://identifiers.org/pubchem.compound/",
                      "PUBCHEM.SUBSTANCE": "http://identifiers.org/pubchem.substance/",
                      "PathWhiz": "http://smpdb.ca/pathways/#",
                      "REACT": "http://www.reactome.org/PathwayBrowser/#/",
                      "REPODB": "http://apps.chiragjpgroup.org/repoDB/",
                      "RGD": "http://identifiers.org/rgd/",
                      "RHEA": "http://identifiers.org/rhea/",
                      "RNACENTRAL": "http://identifiers.org/rnacentral/",
                      "RO": "http://purl.obolibrary.org/obo/RO_",
                      "RTXKG1": "http://kg1endpoint.rtx.ai/",
                      "RXNORM": "http://purl.bioontology.org/ontology/RXNORM/",
                      "ResearchID": "https://publons.com/researcher/",
                      "SEMMEDDB": "https://skr3.nlm.nih.gov/SemMedDB",
                      "SGD": "http://identifiers.org/sgd/",
                      "SIO": "http://semanticscience.org/resource/SIO_",
                      "SMPDB": "http://identifiers.org/smpdb/",
                      "SNOMEDCT": "http://identifiers.org/snomedct/",
                      "SNPEFF": "http://translator.ncats.nih.gov/SNPEFF_",
                      "ScopusID": "https://www.scopus.com/authid/detail.uri?authorId=",
                      "TAXRANK": "http://purl.obolibrary.org/obo/TAXRANK_",
                      "UBERGRAPH": "http://translator.renci.org/ubergraph-axioms.ofn#",
                      "UBERON": "http://purl.obolibrary.org/obo/UBERON_",
                      "UBERON_CORE": "http://purl.obolibrary.org/obo/uberon/core#",
                      "UMLS": "http://identifiers.org/umls/",
                      "UMLSSC": "https://metamap.nlm.nih.gov/Docs/SemanticTypes_2018AB.txt/code#",
                      "UMLSSG": "https://metamap.nlm.nih.gov/Docs/SemGroups_2018.txt/group#",
                      "UMLSST": "https://metamap.nlm.nih.gov/Docs/SemanticTypes_2018AB.txt/type#",
                      "UNII": "http://identifiers.org/unii/",
                      "UPHENO": "http://purl.obolibrary.org/obo/UPHENO_",
                      "UniProtKB": "http://identifiers.org/uniprot/",
                      "VANDF": "https://www.nlm.nih.gov/research/umls/sourcereleasedocs/current/VANDF/",
                      "VMC": "https://github.com/ga4gh/vr-spec/",
                      "WB": "http://identifiers.org/wb/",
                      "WBPhenotype": "http://purl.obolibrary.org/obo/WBPhenotype_",
                      "WBVocab": "http://bio2rdf.org/wormbase_vocabulary",
                      "WIKIDATA": "https://www.wikidata.org/wiki/",
                      "WIKIDATA_PROPERTY": "https://www.wikidata.org/wiki/Property:",
                      "WIKIPATHWAYS": "http://identifiers.org/wikipathways/",
                      "WormBase": "https://www.wormbase.org/get?name=",
                      "ZFIN": "http://identifiers.org/zfin/",
                      "ZP": "http://purl.obolibrary.org/obo/ZP_",
                      "alliancegenome": "https://www.alliancegenome.org/",
                      "biolink": "https://w3id.org/biolink/vocab/",
                      "biolinkml": "https://w3id.org/biolink/biolinkml/",
                      "chembio": "http://translator.ncats.nih.gov/chembio_",
                      "dcterms": "http://purl.org/dc/terms/",
                      "dictyBase": "http://dictybase.org/gene/",
                      "doi": "https://doi.org/",
                      "fabio": "http://purl.org/spar/fabio/",
                      "foaf": "http://xmlns.com/foaf/0.1/",
                      "foodb.compound": "http://foodb.ca/compounds/",
                      "gff3": "https://github.com/The-Sequence-Ontology/Specifications/blob/master/gff3.md#",
                      "gpi": "https://github.com/geneontology/go-annotation/blob/master/specs/gpad-gpi-2-0.md#",
                      "gtpo": "https://rdf.guidetopharmacology.org/ns/gtpo#",
                      "hetio": "http://translator.ncats.nih.gov/hetio_",
                      "interpro": "https://www.ebi.ac.uk/interpro/entry/",
                      "isbn": "https://www.isbn-international.org/identifier/",
                      "isni": "https://isni.org/isni/",
                      "issn": "https://portal.issn.org/resource/ISSN/",
                      "medgen": "https://www.ncbi.nlm.nih.gov/medgen/",
                      "oboformat": "http://www.geneontology.org/formats/oboInOWL#",
                      "pav": "http://purl.org/pav/",
                      "prov": "http://www.w3.org/ns/prov#",
                      "qud": "http://qudt.org/1.1/schema/qudt#",
                      "rdf": "http://www.w3.org/1999/02/22-rdf-syntax-ns#",
                      "rdfs": "http://www.w3.org/2000/01/rdf-schema#",
                      "skos": "https://www.w3.org/TR/skos-reference/#",
                      "wgs": "http://www.w3.org/2003/01/geo/wgs84_pos",
                      "xsd": "http://www.w3.org/2001/XMLSchema#",
                      "@vocab": "https://w3id.org/biolink/vocab/"}

    @staticmethod
    def get_curie_purl(curie):
        # Split into prefix and suffix
        suffix = curie.split(":")[1]
        prefix = curie.split(":")[0]

        # Check to see if the prefix exists in the hash
        if prefix not in BioLinkPURLerizer.biolink_lookup:
            return None

        return f"{BioLinkPURLerizer.biolink_lookup[prefix]}{suffix}"


if __name__ == "__main__":
    import doctest

    doctest.testmod()
