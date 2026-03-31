# mathcompiler_project
Math Compiler — Full Project Explanation
What is this project?
It's a math calculator app but built like a real compiler. Instead of just computing 3 + 4, it processes the expression the same way programming languages like Python or C process your code — in stages.

The Big Picture
You type:  (3 + 4) * 2
              ↓
         [ LEXER ]        → breaks into tokens
         [ PARSER ]       → builds a tree
         [ EVALUATOR ]    → computes the answer
              ↓
         Result: 14       → saved to database

The 3 Compiler Stages
Stage 1 — Lexer (Tokenizer)
Takes your raw text and breaks it into small pieces called tokens. Think of it like breaking a sentence into individual words.
Input:   (3 + 4) * 2
Tokens:  [LPAREN] [NUM:3] [OP:+] [NUM:4] [RPAREN] [OP:*] [NUM:2]
Stage 2 — Parser
Takes those tokens and builds an Abstract Syntax Tree (AST) — a tree structure that respects math rules like "multiply before add."
        *
       / \
      +   2
     / \
    3   4
This tree shows that 3 + 4 happens first (inside the parentheses), then the result is multiplied by 2.
Stage 3 — Evaluator
Walks the tree from bottom to top and computes the answer:

3 + 4 = 7
7 * 2 = 14


Project Structure
The project has two parts — a backend and a frontend.
Backend (app.py)

Written in Python
Runs a web server on your computer at localhost:8000
Contains all 3 compiler stages (Lexer, Parser, Evaluator)
Saves every calculation to a database (history.db) using SQLite
Has a REST API so the frontend can talk to it

Frontend (index.html)

The visual calculator you see in the browser
Has a button pad for clicking numbers and operators
Has a text box so you can type expressions directly
Shows the tokens live after each calculation
Draws the AST tree visually on a canvas
Shows your calculation history in the sidebar
Shows stats — total calculations, average result, most used operator


How they talk to each other
Browser (frontend)
      ↓  sends expression via HTTP
Python server (backend)
      ↓  runs the compiler
      ↓  saves result to SQLite database
      ↑  sends back result + tokens + AST
Browser (frontend)
      ↓  displays result, draws tree, updates history

What operators are supported
OperatorMeaningExample+Addition3 + 4 = 7-Subtraction10 - 3 = 7*Multiplication3 * 4 = 12/Division10 / 4 = 2.5%Modulo (remainder)17 % 5 = 2^Power2 ^ 10 = 1024( )Parentheses(3 + 4) * 2 = 14-Unary minus-5 + 3 = -2
Operator precedence is handled correctly — * and / always happen before + and -, and ^ happens before everything.

What gets saved to the database
Every time you press =, the backend saves:

The expression you typed
The result
The tokens
The AST (as JSON)
The date and time

This is why your history persists — even if you refresh the browser, your past calculations are still there.

What makes this different from a normal calculator
A normal calculator evaluates expressions left to right with simple logic. This project works like a real language compiler — the same fundamental architecture used to build Python, JavaScript, and C. Understanding this project gives you the foundation to build your own programming language.
