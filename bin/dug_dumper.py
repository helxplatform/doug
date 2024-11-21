"""
The Dug Dumper allows you to dump certain kinds of content from a Dug instance.
"""

import click

@click.command()
@click.argument('output', type=click.Path(exists=False), required=True)
@click.option('--mds-metadata-endpoint', '--mds', default=DEFAULT_MDS_ENDPOINT,
              help='The MDS metadata endpoint to use, e.g. https://healdata.org/mds/metadata')
@click.option('--limit', default=MDS_DEFAULT_LIMIT, help='The maximum number of entries to retrieve from the Platform '
                                                         'MDS. Note that some MDS instances have their own built-in '
                                                         'limit; if you hit that limit, you will need to update the '
                                                         'code to support offsets.')
def dug_dumper():
    pass

# Run dug_dumper() if not used as a library.
if __name__ == "__main__":
    dug_dumper()