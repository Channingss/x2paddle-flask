from elasticsearch_dsl import  Document, Keyword ,Text,Ip

class Model(Document):
    ip= Text()
    email = Text()
    log = Text()
    model_dir = Text()
    class Index:
        name = 'flask'
    def save(self, ** kwargs):
        return super(Model, self).save(** kwargs)