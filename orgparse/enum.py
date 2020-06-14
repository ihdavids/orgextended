class Enum(set):
    def __getitem__(self, name):
    	if name in self:
    		return name

    def __getattr__(self, name):
        if name in self:
            return name
        raise AttributeError