import os
import site
site.addsitedir(os.path.abspath(os.path.dirname(__file__) + '/libs'))

def classFactory(iface):
    from .cotraveler import CoTraveler
    return CoTraveler(iface)
