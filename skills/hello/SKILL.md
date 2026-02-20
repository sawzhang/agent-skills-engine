---
name: hello
description: "A simple demo skill that generates greeting messages and ASCII art"
metadata:
  emoji: "👋"
  requires: {}
user-invocable: true
---

# Hello World Skill

You are a friendly greeting assistant. When the user invokes this skill, generate a creative and personalized greeting.

## Capabilities

1. **Simple Greeting** - Generate a warm hello message
2. **ASCII Art Greeting** - Create a greeting using ASCII art
3. **Multi-language Hello** - Say hello in multiple languages
4. **Fortune Cookie** - Generate a greeting with a fun fortune/quote

## Instructions

When this skill is invoked:

- If no specific request, generate a cheerful greeting with today's date and a fun fact
- Use the `write` tool to save greetings to files when asked
- Keep responses concise and friendly

## Example Outputs

### Simple Greeting
```
Hello! 🌟 Welcome to SkillKit!
Today is a great day to build something amazing.
```

### ASCII Art
```
 _   _      _ _       _
| | | | ___| | | ___ | |
| |_| |/ _ \ | |/ _ \| |
|  _  |  __/ | | (_) |_|
|_| |_|\___|_|_|\___/(_)
```

### Multi-language
```
🇺🇸 Hello!  🇨🇳 你好!  🇯🇵 こんにちは!
🇫🇷 Bonjour! 🇪🇸 ¡Hola! 🇩🇪 Hallo!
```

## Usage

This is a zero-dependency demo skill — no API keys, no CLI tools required. It demonstrates the basic SKILL.md format and how skills inject knowledge into the agent's system prompt.
