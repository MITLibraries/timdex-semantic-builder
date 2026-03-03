from lambdas import my_function


def test_my_function():
    assert (
        my_function.lambda_handler({}, {}) == "You have successfully called this lambda!"
    )
