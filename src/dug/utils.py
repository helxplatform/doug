class ObjectFactory:
    def __init__(self):
        self._builders = {}

    def register_builder(self, key, builder):
        self._builders[key] = builder

    def create(self, key, **kwargs):
        builder = self._builders.get(key)
        if not builder:
            raise ValueError(key)
        return builder(**kwargs)

    def get_builder_types(self):
        return list(self._builders.keys())


def complex_handler(obj):
    if hasattr(obj, 'jsonable'):
        return obj.jsonable()
    else:
        raise TypeError(f'Object of type {type(obj)} with value of {type(obj)} is not JSON serializable')


def get_dbgap_var_link(study_id, variable_id):
    base_url = "https://www.ncbi.nlm.nih.gov/projects/gap/cgi-bin/variable.cgi"
    return f'{base_url}?study_id={study_id}&phv={variable_id}'


def get_dbgap_study_link(study_id):
    base_url = "https://www.ncbi.nlm.nih.gov/projects/gap/cgi-bin/study.cgi"
    return f'{base_url}?study_id={study_id}'

def get_nida_study_link(study_id):
    base_url = "https://datashare.nida.nih.gov/study"
    return f'{base_url}/{study_id}'
