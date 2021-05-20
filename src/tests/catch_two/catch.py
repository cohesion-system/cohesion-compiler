def catch_two():
    try:
      result = cohesion.activity.hello(timeout=120)
    except (LockError, DummyError) as e:
      error = cohesion.activity.handle_error()
    except DBError as db:
      db_error = cohesion.activity.handle_db_error()
    return result
