def go():
    with cohesion.parallel() as p:
        with p.thread():
            # this runs in parallel
            pass
        with p.thread():
            # to this
            pass

        with p.thread():
            # these can nest
            with cohesion.parallel() as q:
                with q.thread():
                    pass
                with q.thread():
                    pass

