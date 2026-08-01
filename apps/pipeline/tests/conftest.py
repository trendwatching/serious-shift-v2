def pytest_addoption(parser):
    parser.addoption(
        "--update-golden",
        action="store_true",
        default=False,
        help="Re-record golden fixtures instead of asserting against them.",
    )
