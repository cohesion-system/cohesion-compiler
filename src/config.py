class Config:
    def __init__(self, path: str = '', obj = None):
        self.config = {}
        try:
            with open(path) as f:
                configstr = f.read()
                self.config = json.loads(configstr)
        except FileNotFoundError:
            pass

        self.defaults = {
            "use_router_func": False,
            "region": 'us-east-1',
            "account_id": "set_account_id_in_config"
        }

        # initialize by obj, if provided
        #print("Got obj = %s" % obj)
        if obj != None:
            for k in obj.keys():
                self.set(k, obj[k])

    def _valid_keys(self):
        return ['use_router_func',
                'region',
                'account_id']
        
    def get(self, key):
        if key in self.config:
            return self.config[key]
        elif key in self.defaults:
            return self.defaults[key]
        else:
            return None

    def set(self, key, value):
        self.config[key] = value
