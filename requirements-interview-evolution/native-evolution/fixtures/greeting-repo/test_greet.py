import unittest

from greet import greeting, main


class GreetingTests(unittest.TestCase):
    def test_exact_output(self) -> None:
        self.assertEqual(greeting("Ada"), "Hello, Ada!")

    def test_argument_count(self) -> None:
        self.assertEqual(main([]), 2)
        self.assertEqual(main(["Ada", "Lovelace"]), 2)


if __name__ == "__main__":
    unittest.main()
