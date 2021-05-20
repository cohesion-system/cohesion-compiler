

# Spot instance provisioning library
from cohesion import spot

def myWorkflow(args):

    #
    # Create (and destroy) a Spot Instance
    #
    with cohesion.spotInstance('m5.large'):
        #
        # Cohesion can output code to deploy the body here into the
        # spot instance, and communicate via the SFN Activity system
        #
        doExpensiveStuff()
