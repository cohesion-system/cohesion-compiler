def trycatch():
    try:
        cohesion.Lambda.foo()
    except States.ALL:
        cohesion.Lambda.bar()
    cohesion.Lambda.x()
