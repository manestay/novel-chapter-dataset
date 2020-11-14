# Gutenberg RDF parser

Parse Gutenberg RDF file to python dict.

Approach:

- use xml2json convert rdf xml to json(will miss some data)
- refine the above json
- use rdflib to extract missing data

## xml to json

    ./xml2json.py -t xml2json --strip_namespace --strip_newlines --strip_text samples/pg6899.rdf
