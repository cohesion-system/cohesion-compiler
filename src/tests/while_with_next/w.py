
def w(args):
    ms = args['messages']
    while len(m) > 0:
        m = ms.pop()
        if m['skip']:
            continue
        cohesion.Lambda.process(m)
