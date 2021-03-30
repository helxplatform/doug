
# Dug: digging up dark data

## What is Dug?
Dug is a framework for semantic search over biological data, developed for the NHLBI BioData Catalyst Project.  Dug applies semantic web and knowledge graph methods to improve the [FAIR](https://www.go-fair.org/fair-principles/)-ness of research data in the NHLBI BioData Catalyst Ecosystem.

## Why is Dug?
In general, biological data are messy and lack global standards.  As an example, while [dbGaP](https://www.ncbi.nlm.nih.gov/gap/) is a rich source of metadata about biomedical knowledge derived from clinical research like the underutilized [TOPMed](https://www.nhlbiwgs.org/) data sets, there are no standards governing the variable names nor is there any mapping of variables to ontologies within the system. Separate efforts, like the [65 phenos project](https://www.nhlbiwgs.org/dcc-pheno) undertaken by the TOPMed DCC, have been successful at harmonizing TOPMed variables across datasets.  However, finding unharmonized dbGaP variables can be a challenge for resaerchers to find via text-based search - a key obstacle to leveraging this knowledge is the lack of researcher tools to navigate from a set of concepts of interest towards relevant study variables. In a word, **search**. 

While other approaches to searching this data exist, our focus is **semantic search**. For us, "relevant" is defined as having a basis in curated, peer reviewed ontologically represented biomedical knowledge. Given a search term, Dug returns results that are related based on connections in ontological biomedical knowledge graphs.  These results are 'auditable' in that the underlying knowledge graph provided to the user by Dug helps explain the results, allowing a researcher to use their expertise in determining whether the result is relevant to them.  Thus, Dug understands that "Heart attack" and "Myocardial infraction" are conceptually the same thing, offering an improvement over purely text-based (lexical) search.

**TODO: Image here**

## How does Dug work?
To achieve this, we annotate metadata with terms from [biomedical ontologies](http://www.obofoundry.org/) and contextualize them within a unifying [upper ontology](https://biolink.github.io/biolink-model/), allowing study data to be federated with [larger knowledge graphs](https://researchsoftwareinstitute.github.io/data-translator/) and create a full text search index based on those knowledge graphs.

Further, Dug organizes variables by concept (ontological term), so in addition to providing semantic search results, it functions as a **first-step automated harmonization tool**, as well as displaying manually-harmonized results such as the TOPMed phenotype.  For example, if a researcher were to search "heart attack", the TOPMed harmonized phenotype concept "Myocardial Infarction" would be returned, as well as any other relevant ontological terms such as [MONDO:5068 - myocardial infarction (disease)](http://purl.obolibrary.org/obo/MONDO_0005068).  Relevant variables are returned below these concepts, connected to them through external, manual efforts (e.g. TOPMed) or automatically through the annotation process.

**TODO: Image Needed**

Finally, Dug is **data structure-agnostic**, meaning it can easily make any collection of biological objects searchable. Dug can search over variables in BioData Catalyst for which metadata is available, which at the time of writing is dbGaP variables and harmonized TOPMed phenotype concepts.  In the near future we anticipate enabling search over other types of data as they become avaible in BioData Catalyst, such as DICOM image data, COVID clinical trial data, etc.  Dug comprises three interconnected data structures:

1. **Variables**: A variable is the most granular element of biomedical data that we deal with, and contains metadata about the variable itself (name, description), any relevant dataset metadata, and study metadata about the study to which the variable belongs.  
2. **Concepts**: Concepts are semantic organizers of variables, and occasionally other concepts.  They are either extant (TOPmed phenotype concepts) or generated via annotation of variable metadata (ontological terms) 
3. **Knowledge Graphs**: Knowledge graphs connect concepts with other concepts, contextualized within the upper ontology biolink model.  It enables semantic search over concepts and their constitutent variables.


## The Dug Framework
The Dug Framework consists of five primary domains:

1. **Load** - In the load step, raw (meta)data is loaded and transformed into a format that can be understood and manipulated by Dug
2. **Annotate** - The annotate step leverages [Monarch Initiative APIs](https://api.monarchinitiative.org/api/) to perform named entity recognition on natural language prose to extract ontology identifiers (concepts) from the source datasets (e.g. study metadata, harmonized variable metadata, COPDGene DICOM images, etc.). It also uses Translator normalization services to find preferred identifiers and [Biolink upper ontology](https://biolink.github.io/biolink-model/) types for each extracted identifier.
3. **Crawl** - The concepts generated in the annotate step are then 'crawled', i.e. preconfigured queries using each concept are sent to TranQL (Translator Query Language) to find connected concepts.  The Biolink upper ontology enables the queries to be configured in a language that TranQL understands. Translator services enable TranQL queries that span TOPMed, [ROBOKOP](https://researchsoftwareinstitute.github.io/data-translator/apps/robokop), [ICEES](https://researchsoftwareinstitute.github.io/data-translator/apps/icees), and other reasoners to output knowledge graph.  The resulting knowledge grpah answers enable Dug to perform semantic search as well as link out to related biological concepts that could create unique insight.
4. **Index** - After the crawl step, the three Dug data structures are indexed - variables (from the load step), concepts (from the annotate step), and the knowledge graph answers returend from query.  These structures are indexed as documents in separate indices of Elasticsearch.
5. **Search** - Dug employs a REST API to enable full-text, semantic search of the documents indexed within Elasticsearch.

The methodology, from start to finish, reads raw metadata, annotates it with ontological terms, normalizes those terms, runs queries based on these terms along pre-configured lines, turns the resulting metadata, annotations, and knowledge graphs into documents, and indexes those documents in a full text search engine.

**TODO: Update Image of Dug Framework**

## Development
### Overview
A docker-compose is provided that runs five services:
* Redis
* Neo4J
* Elasticsearch
* The Dug Search OpenAPI
* [The Dug Search Client](https://github.com/helxplatform/dug-search-client)

The first four services run in one container, and the search client runs in a separate container.

This system can be started with the following command:

| Command             | Description                | Example          |
| ------------------- | -------------------------- | ---------------- |
| bin/dug stack       | Runs all services          | bin/dug stack up |

**Developers:** Internal to bin/dug, an environment file is automatically created. That file is in `docker/.env`.
If you are running in development, and are not using a public IP address and hostname, you'll want to create a separate `.env` file to allow programs to connect to the docker containers as services. This matters if, for example, you want to run bin/test, as the clients in that test need to know how to connect to each of the services they call. Copy the generated `docker/.env` to `docker/.env.dev`. Change all hostnames (`NEO4J_HOST`, `ELASTIC_API_HOST`, `REDIS_HOST`) to `localhost`.That should do it. Be sure to keep the generated passwords from the generated .env the same. 

Similarly, when spinning up the Dug Search Client locally, the .env file in the dug-search-client repo most be changed to the following:
```
REACT_APP_DUG_URL=http://localhost:5551
CLIENT_PORT=80
```

This ensures that the Dug Search Client connects to the local Dug Search OpenAPI instead of one of the user-facing deployments

### Local Deployment
User-facing deployments of Dug exist, however to test new functionality it is best to spin up a local deployment. The following steps detail deployment of Dug on a local machine.  These steps assume that the repository has been cloned, the virtual environment has been created per the `requirements.txt` file, and commands are being entered in the command line at the /dug repository.

**Start System, Activate Virtual Environment**

* Start the system in headless mode: `bin/dug stack up -d`
* Activate the virtual environment: `source venv/bin/activate`

**File Management**

* Unzip the tarball at dug/data: `COPYFILE_DISABLE=1 tar -xf data/data_dicts_with_gapexchange.tar -C ./data`
* Make the directory to house study metadata: `mkdir ./data/gapexchange`
* Move all of the study metadata files to this directory: `find ./data/data -type f -name 'GapExchange*' -exec mv -t ./data/gapexchange {} +`

**Crawl**

In the current instantiation of Dug, 'crawl' refers to the combined process of loading data into Dug, annotating it, running queries on the concepts coming from annotation, and indexing the results in Elasticsearch for later query.  Currently the order of operatations matters here; perform them in the steps listed below.

* Crawl dbGaP variables: `bin/dug crawl_dir data/data`
* Crawl TOPMed variables: `bin/dug crawl_by_concept --crawl-file ./data/topmed_variables_v1.0.csv`
* Crawl study metadata files to update variable metadata: `bin/dug crawl_dir data/gapexchange`

The run-time of crawl locally is quite long, on the order of hours.

## The Dug Data Development Kit (DDK)

**TODO: Do we need this section?**

Dug provides a tool chain for the ingest, annotation, knowledge graph representation, query, crawling, indexing, and search of datasets with metadata. The following sections provide an overview of the relevant components.

### Link
(Note: Link is a depcrecated component of the Dug Framework)
Link ingests raw dbGaP study metadata and performs semantic annotation by:
* Parsing a TOPMed data dictionary XML file to extract variables.
* Using the Monarch SciGraph named entity recognizer to identify ontology terms.
* Using the Translator SRI identifier normalization service to:
  * Select a preferred identifier for the entity
  * Determine the BioLink types applying to each entity
* Writing each variable with its annotations as a JSON object to a file.

### Load
(Note: Load is a deprecated component of the Dug Framework)
* Converts the annotation format written in the steps above to a KGX graph
* Inserts that graph into a Neo4J database.

In phase-1, we query Neo4J to create knowledge graphs. In phase-2 we'll use the Neo4J to create a Translator Knowledge Provider API. That API will be integrated using TranQL with other Translator reasoners like ROBOKOP. This will allow us to build more sophisticated graphs spanning federated ontological knowledge.

### Crawl

* Runs graph queries to TranQL and caches knowledge graph responses in Redis.

### Index

* Consumes knowledge graphs produced by the crawl.
* Uses connections in the graph to create documents including both full text of variable descriptions and ontology terms.
* Produces a queryable full text index of the variable set.

### Search API

* Presents an OpenAPI compliant REST interface
* Provides a scalable microservice suitable as an Internet endpoint. 

### Ingest

Data formats for harmonized variables appear to be in flux, hence the multiple approaches. More on this soon.

| Command           | Description                                         | Example                  |
| ----------------- | --------------------------------------------------- | ------------------------ |
| bin/dug link      | Use NLP, etc to add ontology identifiers and types. | bin/dug link {input}     |
| bin/dug load      | Create a knowledge graph database.                  | bin/dug load {input}     |

There are three sets of example metadata files in the repo.
* A COPDGene dbGaP metadata file is at `data/dd.xml`
* A harmonized variable metadata CSV is at `data/harmonized_variable_DD.csv`
* Files with names starting with: `data/topmed_*`

This last format seems to be the go-forward TOPMed harmonized variable form.

These can be run with 
```
bin/dug link data/dd.xml
bin/dug load data/dd_tagged.json
```
or 
```
bin/dug link data/harmonized_variable_DD.csv
bin/dug load data/harmoinzed_variable_DD_tagged.json
```
or
```
bin/dug link data/topmed_variables_v1.0.csv [--index x]
```
The first two formats will likely go away.
The last format
* Consists of two sets of files following that naming convention.
* Combines the link and load phases into link.
* Optionally allows the --index <arg> flag. This will run graph queries and index data in Elasticsearch.
 
### Crawl & Index

| Command        | Description                                                       | Example              |
| -------------- | ----------------------------------------------------------------- | -------------------- |
| bin/dug crawl  | Execute graph queries and accumulate knowledge graphs in response.| bin/dug crawl        |
| bin/dug index  | Analyze crawled knowledge graphs and create search engine indices.| bin/dug index        |
| bin/dug query  | Test the index by querying the search engine from Python.         | bin/dug query {text} |
 
### Search API

Exposing the Elasticsearch interface to the internet is strongly discouraged for security reasons. Instead, we have a REST API. We'll use this as a place to enforce a schema and validate requests so that the search engine's network endpoint is strictly internal.
| Command        | Description           | Example                              |
| -------------- | --------------------- | ------------------------------------ |
| bin/dug api    | Run the REST API.     | bin/dug api [--debug] [--port={int}] |

To call the API endpoint using curl:
| Command             | Description           | Example                   |
| ------------------- | --------------------- | ------------------------- |
| bin/dug query_api   | Call the REST API.    | bin/dug query_api {query} |

## Testing
**TODO: Do we need to update this section in the code?**


Dug's automated functional tests:
* Delete the test index
* Execute the link and load phases for the dbGaP data dictionary and harmonized variables.
* Execute the crawl and index phases.
* Execute a number of searches over the generated search index.

| Command             | Description                    | Example      |
| ------------------- | ------------------------------ | ------------ |
| bin/dug test        | Run automated functional tests | bin/dug test |

Once the test is complete, a command line search shows the contents of the index:
![image](https://user-images.githubusercontent.com/306971/77009780-e939f580-693e-11ea-8a02-ca2fd59d4366.png)
**Figure 4**: A command line query using the Dug Search OpenAPI to query the Elasticsearch index for a term.


## Python Testing
* To run the python unit tests, type: `bin/dug pytests`

## Data Formats

Until data formats stabilize, the best approach is to have a look at the raw data [here](https://github.com/helxplatform/dug/tree/master/data).

## Next Steps

Recent:
* [x] Develop Kubernetes artifacts to move from development to a public API.
* [x] Apply Plater & Automat to serve the Neo4J as our TOPMed metadata API.
* [x] Demonstrate a TranQL query incorporating this data with ROBOKOP

Finalizing Phase 1:
* [ ] Textual descriptions are aggregated into a name field in the JSON document indexed in Elastic. These should be broken out into clearly named fields.
* [ ] The fields mentioned above should be rendered in the user interface.
* [ ] Add automated unit tests and a Travis build.

Phase 2:
* [ ] Use TranQL queries to populate Elasticsearch (as shown elsewhere in this repo).
* [ ] Several identifiers returned by the Monarch NLP are not found by the SRI normalizer. The good news is, several of these missing identifiers are quite important (BMI, etc) so once we get them included in normalization, our annotation should be improved.
  * Error logs from data dictionary annotation are [here](https://github.com/helxplatform/dug/blob/master/dug/log/dd_norm_fail.log).
  * Logs from harmonized variable annotation are [here](https://github.com/helxplatform/dug/blob/master/dug/log/harm_norm_fail.log).
* [x] The input here is a TOPMed DD. Investigate starting the pipeline from harmonized variables.
  * We now have the ability to (roughly) parse harmonized variables from their standard CSV format.
  * Several issues arose around formatting, the need for a study id, and a few other things. 
  * But the overall approach seems feasible.
* [x] Document the crawl, index, and search (API) components of Dug here.

## Future
* [ ] Refine knowledge graph queries and indexing analytics to improve result relevance.
* [ ] Incorporate synonyms and additional NLP approaches.
* [ ] Parallelize steps with Spark.
* [ ] Develop a frictionless KGX interface to Spark.
* [ ] Use Morpheus Cypher for query.


