import logging
from app.bot import DiceGameBot


def main():
    logging.basicConfig(
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        level=logging.INFO
    )

    bot = DiceGameBot()
    bot.run()


if __name__ == "__main__":
    main()