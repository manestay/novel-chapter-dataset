"""
number_lib.py

Functions to work with various representations of numbers.
"""

import re


def str_to_int(inp, numwords={}):
    result = None
    try:
        result = int(inp)
    except:
        try:
            result = roman_to_int(inp)
        except:
            try:
                result = numword_to_int(inp, numwords)
            except:
                raise Exception
    return result


def numword_to_int(textnum, numwords={}, use_and=True):
    textnum = textnum.replace('-', ' ')
    numwords = numwords or get_numwords(use_and=use_and)

    current = result = 0
    for word in textnum.lower().split():
        if word not in numwords:
            raise Exception("Illegal word: " + word)

        scale, increment = numwords[word]
        current = current * scale + increment
        if scale > 100:
            result += current
            current = 0

    return result + current


def int_to_roman(input):
    """
    Convert an integer to Roman numerals.
    """
    if not isinstance(input, int):
        raise TypeError
    if not 0 < input < 4000:
        raise ValueError
    ints = (1000, 900,  500, 400, 100,  90, 50,  40, 10,  9,   5,  4,   1)
    nums = ('M',  'CM', 'D', 'CD', 'C', 'XC', 'L', 'XL', 'X', 'IX', 'V', 'IV', 'I')
    result = ""
    for i in range(len(ints)):
        count = int(input / ints[i])
        result += nums[i] * count
        input -= ints[i] * count
    return result


def roman_to_int(input):
    """
    Convert a roman numeral to an integer.
    """
    if not isinstance(input, str):
        raise TypeError
    input = input.upper()
    nums = ['M', 'D', 'C', 'L', 'X', 'V', 'I']
    ints = [1000, 500, 100, 50,  10,  5,   1]
    places = []
    for c in input:
        if c not in nums:
            raise ValueError
    for i in range(len(input)):
        c = input[i]
        value = ints[nums.index(c)]
        # If the next place holds a larger number, this value is negative.
        try:
            nextvalue = ints[nums.index(input[i + 1])]
            if nextvalue > value:
                value *= -1
        except IndexError:
            # there is no next place.
            pass
        places.append(value)
    sum = 0
    for n in places:
        sum += n
    # Easiest test for validity...
    if int_to_roman(sum) == input:
        return sum
    else:
        raise ValueError


def get_numwords(use_and=True):
    numwords = {}
    units = [
        "zero", "one", "two", "three", "four", "five", "six", "seven", "eight",
        "nine", "ten", "eleven", "twelve", "thirteen", "fourteen", "fifteen",
        "sixteen", "seventeen", "eighteen", "nineteen",
    ]

    tens = ["", "", "twenty", "thirty", "forty", "fifty", "sixty", "seventy", "eighty", "ninety"]

    scales = ["hundred", "thousand", "million", "billion", "trillion"]

    if use_and:
        numwords["and"] = (1, 0)
    for idx, word in enumerate(units):
        numwords[word] = (1, idx)
    for idx, word in enumerate(tens):
        numwords[word] = (1, idx * 10)
    for idx, word in enumerate(scales):
        numwords[word] = (10 ** (idx * 3 or 2), 0)
    return numwords


numwords = get_numwords(use_and=False)
keys = set(numwords.keys())
keys.remove('')
RE_NUMWORD = re.compile(r'(\b({})-?\b)+'.format('|'.join(keys)), re.IGNORECASE)
