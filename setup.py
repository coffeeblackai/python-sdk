from setuptools import setup, find_packages

with open("README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()

setup(
    name="coffeeblack",
    version="0.1.5",
    author="CoffeeBlack AI",
    author_email="info@coffeeblack.ai",
    description="Python client for interacting with the CoffeeBlack visual reasoning API",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/coffeeblack/sdk",
    packages=find_packages(),
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
    ],
    python_requires=">=3.7",
    install_requires=[
        "pyautogui",
        "aiohttp",
        "asyncio",
        "pillow",
        "numpy",
        "opencv-python",
        "mss",
    ],
) 