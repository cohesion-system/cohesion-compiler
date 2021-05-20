
def main():
    myList = [1,2,3]

    # One way to do parallel map:
    # how do we get the result, tho?
    with cohesion.parallel_list(mylist) as pl:
        for p in pl:
            cohesion.Lambda.do_stuff(p)

            
    # Another:
    result = cohesion.map(mylist, cohesion.Lambda.do_stuff)

