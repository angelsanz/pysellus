import inspect
from functools import partial

from pysellus import integrations

stream_to_testers = {}


def register(function_list):
    for fn in function_list:
        fn()
    return stream_to_testers


def expect(stream):
    """
    expect :: rx.Observable -> ([(Any -> Boolean)] -> IO)

    Given an observable, return a function that takes a function tuple, and maps them

    Store our caller function name for future use (see _get_name_of_expect_caller)

    """
    test_name = _get_name_of_expect_caller()

    def tests_registrar(*testers):
        """
        tests_registrar :: List (Any -> Boolean) -> IO

        Given a function tuple, define a wrapper around it
        and map it against the original stream given to expect.

        For each function in the tuple, define a wrapper around it.
        This wrapper function takes an element (Any) and gives it to the original function.

        This function takes an element, and performs a check on it. If the test returns false,
        send a message to the appropiate integration (see integrations#notify_{message,error})

        """
        for tester in testers:
            _register_tester_for_stream(
                stream,
                partial(_on_failure_wrapper, test_name, tester)
            )

    return tests_registrar


def _on_failure_wrapper(test_name, tester, element):
    """
    Given a test name, a tester, and an element, wrap the tester call
    with the given element in a try-except block. Whenever the test fails,
    or an exception occurs, notify the assigned subject of it, including
    the test name where it failed.

    TODO: Add _on_match_wrapper, like `if tester(element)`
          Also, the description of the payload message should change

    """

    payload_message = _make_message_payload(
        integrations.registered_integrations[test_name]['test_description'],
        tester.__name__,
        element
    )
    try:
        if not tester(element):
            integrations.notify_element(test_name, payload_message)
    except Exception as e:
        # In theory, no exception happening above could crash the application,
        # so, again, in _theory_, this should be safe.

        # Catch any errors that could happen inside the tester, and send that to
        # whoever is interested in the result
        payload_message['error'] = e
        integrations.notify_error(test_name, payload_message)


def _get_name_of_expect_caller():
    """
    _get_name_of_expect_caller :: -> String

    Get the function name of the caller to the `expect` function

    Note: This function should only be called inside the `expect` function. Any other use can not
    be guaranteed to work

    The stack is a list of frame records. The first entry in it represents the caller,
    the last entry represents the outermost call on the stack.

    As we want the parent of expect, we should get the fourth element of the stack

    Each frame record  is a tuple of six items: the frame object (0), the filename (1),
    the line number of the current line (2), the function name (3), a list of lines of context
    from the source code (4), and the index of the current line within that list (5).

    We want to get the function name, so we will get the [3] element

    Most of this is taken from the docs,
    see https://docs.python.org/3/library/inspect.html#the-interpreter-stack

    """
    # Magic. Do not touch.
    distance_to_setup_function = sum([
        # at the moment, the call stack looks something like this
        # ... more frames
        1,  # call to `pscheck_` function, whose name we want to retrieve
        1,  # call to `expect`
        1,  # call to this function, `_get_name_of_expect_caller`
    ]) - 1  # stack is 0-indexed

    return inspect.stack()[distance_to_setup_function][3]


def _make_message_payload(test_name, tester_name, element):
    """
    _make_message_payload :: String -> String -> Any -> {}

    Create a message payload dictionary with the supplied arguments

    """
    return {
        'test_name': test_name,
        'expect_function': tester_name,
        'element': element
    }


def _register_tester_for_stream(stream, tester):
    """
    _register_tester_for_stream :: rx.Observable -> fn -> IO

    Given an Observable, and a tester function, map the Observable to a list of functions.

    If the given stream already has some functions mapped to it, add the given function to the list

    """
    if stream in stream_to_testers:
        stream_to_testers[stream].append(tester)
    else:
        stream_to_testers[stream] = [tester]
