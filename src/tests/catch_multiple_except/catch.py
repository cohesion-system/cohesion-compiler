def trycatch():
    try:
        cohesion.Lambda.foo()
    except (A, B):
        cohesion.Lambda.bar()
    cohesion.Lambda.x()
