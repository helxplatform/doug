
# Background

Dug applies semantic web and knowledge graph methods to improve the [FAIR](https://www.go-fair.org/fair-principles/)-ness of research data.

As an example, [dbGaP](https://www.ncbi.nlm.nih.gov/gap/) is a rich source of metadata about biomedical knowledge derived from clinical research like the underutilized [TOPMed](https://www.nhlbiwgs.org/) data sets. A key obstacle to leveraging this knowledge is the lack of researcher tools to navigate from a set of concepts of interest towards relevant study variables. In a word, **search**. 

While other approaches to searching this data exist, our focus is semantic search: For us, "relevant" is defined as having a basis in curated, peer reviewed ontologically represented biomedical knowledge. Given a search term, Dug returns results that are related based on connections in ontological biomedical knowledge graphs.

To achieve this, we annotate study metadata with terms from [biomedical ontologies](http://www.obofoundry.org/), contextualize them within a unifying [upper ontology](https://biolink.github.io/biolink-model/) allowing study data to be federated with [larger knowledge graphs](https://researchsoftwareinstitute.github.io/data-translator/), and create a full text search index based on those knowledge graphs.


## Kelsey Outline

## High level installation

```

# Requires Python 3.10 or later

make install

source .env
export $(cut -d= -f1 .env)
export ELASTIC_API_HOST=localhost
export REDIS_HOST=localhost

# make sure there are no port conflicts 
# with redis or other containers 
#  ... I had other containers running

# chmod or chown dug/data dirs as needed

dug crawl data/topmed_variables_v2.0.csv -p "TOPMedTag"
# the above command may take up to 2 hours 
# even with fast hardware.

# test it out:

dug search -q "heart attack" -t "concepts"
dug search -q "heart attack" -t "variables"

```

## How to run a crawl

## Run a search on your local machine

## How to deploy a UI on local machine

## How to wrtie a parser to different input sources

## Config options (extensions available)

## Link to bioinformatics paper for more in-depth information
