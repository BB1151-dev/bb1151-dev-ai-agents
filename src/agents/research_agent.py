'''
🌙 BB1151's Research Agent 🌙
This agent automatically generates trading strategy ideas and logs them to both CSV and ideas.txt

Features:
- Rotates between multiple AI models (DeepSeek-R1, llama3.2, gemma:2b)
- Checks for duplicate ideas before adding them
- Logs ideas to a CSV file with timestamps and model info
- Appends new ideas to the ideas.txt file for RBI Agent processing
- Runs in a continuous loop generating new ideas

Created with ❤️ by BB1151

[] be able to search youtube
[] be able to search the web 
'''

# PROMPT - Edit this to change the type of ideas generated
IDEA_GENERATION_PROMPT = """
You are BB1151's Trading Strategy Idea Generator 🌙

Come up with ONE unique trading strategy idea that can be backtested
The idea should be innovative, specific, and concise (1-2 sentences only).

Focus on one of these areas:
- Technical indicators with unique combinations
- Volume patterns
- Volatility-based strategies
- Liquidation events
- technical indicators that can be backtested


Your response should be ONLY the strategy idea text - no explanations, no introductions, 
no numbering, and no extra formatting. Just the raw idea in 1-2 sentences.

Example good responses:
"A mean-reversion strategy that enters when RSI diverges from price action while volume decreases, with exits based on ATR multiples."
"Identify market regime shifts using a combination of volatility term structure and options skew, trading only when both align."
"""

import os
import time
import csv
import random
from datetime import datetime
from pathlib import Path
from termcolor import cprint, colored
import pandas as pd
import sys
import threading
import shutil
import textwrap

# Import model factory from RBI agent
import sys
project_root = Path(__file__).parent.parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))
from src.models import model_factory
from src.mcp_client import MCPClient

# Define paths
PROJECT_ROOT = Path(__file__).parent.parent.parent  # Points to project root
DATA_DIR = PROJECT_ROOT / "src" / "data" / "rbi_pp_multi"  # 🌙 Using rbi_pp_multi for parallel processing
IDEAS_TXT = DATA_DIR / "ideas.txt"
IDEAS_CSV = DATA_DIR / "strategy_ideas.csv"

# MCP Configuration
MCP_ENABLED = True  # Set to False to disable web research
SMITHERY_CONFIG = {
    "command": "npx",
    "args": ["-y", "mcp-deep-research@latest"],
    "env": {
        "TAVILY_API_KEY": "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",
        "MAX_SEARCH_KEYWORDS": "5",
        "MAX_PLANNING_ROUNDS": "5"
    },
    "timeout": 60  # Increased timeout for deep research
}

# 🎯 TOKEN OPTIMIZATION SETTINGS
MAX_CONTEXT_CHARS = 500  # Maximum characters to send to DeepSeek (was unlimited before!)
REMOVE_LINKS = True  # Remove URLs to save tokens
SUMMARIZE_CONTEXT = True  # Summarize MCP response before sending

# 🌙 STRATEGY TYPE ROTATION - Different research focus each time!
STRATEGY_TYPES = [
    {
        "name": "Single Timeframe",
        "description": "Strategy using one timeframe only",
        "timeframes": ["5m", "15m", "30m", "1h"],
        "focus": "price action, volume, momentum indicators"
    },
    {
        "name": "Multi-Timeframe (2 TFs)",
        "description": "Strategy using primary + 1 informative timeframe",
        "primary_tfs": ["5m", "15m", "30m"],
        "informative_tfs": ["1h", "4h", "1d"],
        "focus": "trend alignment, higher timeframe filters"
    },
    {
        "name": "Multi-Timeframe (3+ TFs)",
        "description": "Strategy using primary + multiple informative timeframes",
        "primary_tfs": ["5m", "15m"],
        "informative_tfs": ["1h", "4h", "1d", "1w"],
        "focus": "multi-timeframe confluence, regime detection"
    },
    {
        "name": "High Frequency",
        "description": "Very short timeframe scalping strategy",
        "timeframes": ["1m", "3m", "5m"],
        "focus": "order flow, microstructure, tick data, bid-ask spread"
    }
]

# Research Configuration for MCP deep-research tool
RESEARCH_TOPIC = "finance"
RESEARCH_KEYWORDS_POOL = [
    ["Bitcoin", "volatility", "volume"],
    ["Ethereum", "DeFi", "momentum"],
    ["crypto", "breakout", "reversal"],
    ["liquidations", "funding", "derivatives"],
    ["on-chain", "whale", "accumulation"]
]

# 🔥 SHORTER QUESTIONS TO SAVE TOKENS!
RESEARCH_QUESTIONS_POOL = [
    "Recent crypto volatility patterns?",
    "Unusual volume or momentum shifts?",
    "Key technical levels broken?",
    "Derivative market signals?",
    "On-chain activity changes?"
]

RESEARCH_ROUNDS = 1  # Reduced from 2 to save tokens!

# Model configurations
MODELS = [
    # {"type": "ollama", "name": "DeepSeek-R1:latest"},
    # {"type": "ollama", "name": "llama3.2:latest"},
    # {"type": "ollama", "name": "gemma:2b"}
    {"type": "deepseek", "name": "deepseek-chat"},
    {"type": "deepseek", "name": "deepseek-reasoner"}
]

# Fun emojis for animation
EMOJIS = ["🚀", "💫", "✨", "🌟", "💎", "🔮", "🌙", "⭐", "🌠", "💰", "📈", "🧠"]
MOON_PHASES = ["🌑", "🌒", "🌓", "🌔", "🌕", "🌖", "🌗", "🌘"]

# Get terminal width for better formatting
TERM_WIDTH = shutil.get_terminal_size().columns

def clear_line():
    """Clear the current line in the terminal"""
    print("\r" + " " * TERM_WIDTH, end="\r", flush=True)

def animate_text(text, color="yellow", bg_color="on_blue", delay=0.03):
    """Animate text with a typewriter effect - terminal friendly with background color"""
    # Make sure we start with a clean line
    clear_line()
    
    # Ensure we're working with a single line of text
    text = ' '.join(text.split())
    
    result = ""
    for char in text:
        result += char
        # Clear the line first to prevent ghosting
        print("\r" + " " * len(result), end="\r", flush=True)
        # Then print the updated text
        print(f"\r{colored(result, color, bg_color)}", end='', flush=True)
        time.sleep(delay)
    
    # End with a newline
    print()  # New line after animation

def animate_loading(duration=3, message="Generating idea", emoji="🌙"):
    """Show a fun loading animation - terminal friendly version with background colors"""
    frames = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]
    colors = ["cyan", "magenta", "blue", "green", "yellow"]
    bg_colors = ["on_blue", "on_magenta", "on_cyan"]
    
    end_time = time.time() + duration
    i = 0
    
    while time.time() < end_time:
        frame = frames[i % len(frames)]
        color = colors[(i // 3) % len(colors)]  # Change color less frequently
        bg_color = bg_colors[(i // 6) % len(bg_colors)]  # Change background even less frequently
        
        # Simple animation that won't flicker
        clear_line()
        print(f"\r{colored(f' {frame} {message} {emoji} ', color, bg_color)}", end="", flush=True)
        
        time.sleep(0.2)  # Slower animation
        i += 1
    
    clear_line()
    print()  # New line after animation

def animate_moon_dev():
    """Show a fun Moon Dev animation - terminal friendly with background colors"""
    moon_dev = [
        "  __  __                         ____                 ",
        " |  \\/  |  ___    ___   _ __   |  _ \\   ___  __   __ ",
        " | |\\/| | / _ \\  / _ \\ | '_ \\  | | | | / _ \\ \\ \\ / / ",
        " | |  | || (_) || (_) || | | | | |_| ||  __/  \\ V /  ",
        " |_|  |_| \\___/  \\___/ |_| |_| |____/  \\___|   \\_/   "
    ]
    
    colors = ["white", "white", "white", "white", "white"]
    bg_colors = ["on_blue", "on_cyan", "on_magenta", "on_green", "on_blue"]
    
    print()  # Start with a blank line
    for i, line in enumerate(moon_dev):
        color = colors[i % len(colors)]
        bg = bg_colors[i % len(bg_colors)]
        cprint(line, color, bg)
        time.sleep(0.3)  # Slower animation
    
    # Add some sparkles
    for _ in range(3):
        emoji = random.choice(EMOJIS)
        position = random.randint(0, min(50, TERM_WIDTH-5))
        print(" " * position + emoji)
        time.sleep(0.3)  # Slower animation

def setup_files():
    """Set up the necessary files if they don't exist"""
    # Create data directory if it doesn't exist
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    
    # Create ideas.txt if it doesn't exist
    if not IDEAS_TXT.exists():
        cprint(f"📝 Creating ideas.txt at {IDEAS_TXT}", "yellow", "on_blue")
        with open(IDEAS_TXT, 'w') as f:
            f.write("# Moon Dev's Trading Strategy Ideas 🌙\n")
            f.write("# One idea per line - Generated by Research Agent 🤖\n")
            f.write("# Format: Strategy idea text (1-2 sentences)\n\n")
    
    # Create ideas CSV if it doesn't exist
    if not IDEAS_CSV.exists():
        cprint(f"📊 Creating ideas CSV at {IDEAS_CSV}", "white", "on_magenta")
        with open(IDEAS_CSV, 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(['timestamp', 'model', 'idea'])

def load_existing_ideas():
    """Load existing ideas from CSV to check for duplicates"""
    if not IDEAS_CSV.exists():
        return set()
    
    try:
        df = pd.read_csv(IDEAS_CSV)
        if 'idea' in df.columns:
            # Convert ideas to lowercase for case-insensitive comparison
            ideas = set(idea.lower() for idea in df['idea'].tolist())
            cprint(f"💾 Loaded {len(ideas)} existing ideas!", "white", "on_blue")
            return ideas
        return set()
    except Exception as e:
        cprint(f"⚠️ Error loading existing ideas: {str(e)}", "red")
        return set()

def is_duplicate(idea, existing_ideas):
    """Check if an idea is a duplicate (case-insensitive)"""
    # Simple exact match check
    if idea.lower() in existing_ideas:
        return True
    
    # Check for high similarity (future enhancement)
    # This could use techniques like cosine similarity with embeddings
    
    return False

def summarize_text(text, max_chars=MAX_CONTEXT_CHARS):
    """Summarize text to save tokens - extract key points only"""
    if not text or len(text) <= max_chars:
        return text
    
    # Remove URLs/links
    if REMOVE_LINKS:
        import re
        text = re.sub(r'http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\(\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+', '', text)
    
    # Split into sentences
    import re
    sentences = re.split(r'[.!?]+', text)
    
    # Keep first few sentences that fit in max_chars
    summary_parts = []
    current_length = 0
    
    for sentence in sentences:
        sentence = sentence.strip()
        if not sentence:
            continue
        
        # Skip if sentence is just a URL or source reference
        if sentence.startswith('http') or sentence.startswith('Source:'):
            continue
            
        if current_length + len(sentence) < max_chars:
            summary_parts.append(sentence)
            current_length += len(sentence)
        else:
            break
    
    summary = '. '.join(summary_parts)
    if summary and not summary.endswith('.'):
        summary += '.'
    
    return summary[:max_chars]

def get_market_context():
    """Fetch live market context from MCP deep-research tool - OPTIMIZED for token savings!"""
    if not MCP_ENABLED:
        return ""
    
    try:
        cprint("\n🌍 Fetching live market context via MCP...", "cyan")
        
        # Initialize MCP client with environment variables
        mcp = MCPClient(
            command=SMITHERY_CONFIG["command"],
            args=SMITHERY_CONFIG["args"],
            timeout=SMITHERY_CONFIG["timeout"],
            env=SMITHERY_CONFIG.get("env")  # Pass environment variables (TAVILY_API_KEY, etc.)
        )
        
        # Find appropriate research tool
        research_tool = mcp.find_tool(["research", "search", "deep"])
        
        if not research_tool:
            cprint("⚠️  No research tool found, skipping MCP context", "yellow")
            mcp.close()
            return ""
        
        cprint(f"🔍 Using tool: {research_tool}", "green")
        
        # 🆕 ROTATE through different questions and keywords each time!
        import random
        selected_question = random.choice(RESEARCH_QUESTIONS_POOL)
        selected_keywords = random.choice(RESEARCH_KEYWORDS_POOL)
        
        # Execute research with proper parameters for deep-research tool
        research_params = {
            "question": selected_question,  # REQUIRED - now rotating!
            "topic": RESEARCH_TOPIC,
            "keywords": selected_keywords,  # Rotating keywords!
            "search_round": RESEARCH_ROUNDS
        }
        
        cprint(f"📝 Research question: {selected_question}", "cyan")
        cprint(f"🔑 Keywords: {', '.join(selected_keywords)}", "cyan")
        
        result = mcp.call_tool(research_tool, research_params)
        mcp.close()
        
        # 🆕 LOG THE COMPLETE MCP RESPONSE
        cprint("\n" + "="*80, "magenta")
        cprint("📥 MCP DEEP-RESEARCH RESPONSE:", "white", "on_magenta", attrs=['bold'])
        cprint("="*80, "magenta")
        
        if isinstance(result, dict):
            import json
            cprint(json.dumps(result, indent=2), "yellow")
        else:
            cprint(str(result), "yellow")
        
        cprint("="*80 + "\n", "magenta")
        
        # 🔥 PARSE & OPTIMIZE - Extract only key insights, NO LINKS!
        context_parts = []
        
        if isinstance(result, dict):
            # Try common field names - but limit length!
            for field in ["summary", "content", "text", "result", "answer"]:
                if field in result and result[field]:
                    text = str(result[field])
                    # Remove URLs
                    if REMOVE_LINKS:
                        import re
                        text = re.sub(r'http[s]?://\S+', '', text)
                    # Take only first 200 chars from each field
                    context_parts.append(text[:200])
            
            # Check for findings/items - ONLY TAKE TOP 2!
            for field in ["findings", "items", "results", "insights"]:
                if field in result and isinstance(result[field], list):
                    # Only top 2 findings to save tokens!
                    for item in result[field][:2]:
                        item_str = str(item)[:100]  # Max 100 chars per finding
                        if REMOVE_LINKS:
                            import re
                            item_str = re.sub(r'http[s]?://\S+', '', item_str)
                        context_parts.append(f"- {item_str}")
            
            # SKIP SOURCES - they're just URLs and waste tokens!
        
        # Fallback: convert result to string but limit size
        if not context_parts:
            result_str = str(result).strip()[:300]  # Max 300 chars
            if result_str and result_str != "None" and result_str != "{}":
                if REMOVE_LINKS:
                    import re
                    result_str = re.sub(r'http[s]?://\S+', '', result_str)
                context_parts.append(result_str)
        
        if context_parts:
            raw_context = "\n".join(context_parts).strip()
            
            # 🎯 SUMMARIZE if still too long!
            if SUMMARIZE_CONTEXT:
                context = summarize_text(raw_context, MAX_CONTEXT_CHARS)
            else:
                context = raw_context[:MAX_CONTEXT_CHARS]
            
            cprint(f"✅ Context optimized: {len(raw_context)} → {len(context)} chars (saved {len(raw_context)-len(context)} chars!)", "green")
            return context
        
        # No useful data
        cprint(f"⚠️  MCP returned empty result", "yellow")
        return ""
        
    except Exception as e:
        cprint(f"⚠️  MCP context fetch failed: {str(e)}", "yellow")
        return ""

def generate_idea(model_config, strategy_type=None):
    """Generate a trading strategy idea using the specified model
    
    Args:
        model_config: Model configuration dict
        strategy_type: Optional strategy type from STRATEGY_TYPES to focus on
    """
    try:
        # Fun animated header
        print("\n" + "=" * min(60, TERM_WIDTH))
        cprint(f" 🧙‍♂️ MOON DEV'S IDEA GENERATOR 🧙‍♂️ ", "white", "on_magenta")
        print("=" * min(60, TERM_WIDTH))
        
        cprint(f"\n🧠 Using {model_config['type']} - {model_config['name']}...", "cyan")
        time.sleep(0.5)  # Pause for readability
        
        # Simple loading animation
        print()
        emoji = random.choice(EMOJIS)
        cprint(f"🔮 Asking {model_config['name']} for trading ideas...", "yellow", "on_blue")
        time.sleep(0.5)  # Pause for readability
        
        # Show generation progress with black text on white background
        progress_messages = [
            "🔍 Scanning market patterns...",
            "📊 Analyzing technical indicators...",
            "🧮 Calculating optimal parameters...",
            "🔮 Exploring strategy combinations...",
            "💡 Formulating unique approach...",
            "🌟 Polishing trading concept...",
            "🚀 Finalizing strategy idea..."
        ]
        
        # Display progress messages with animation
        for msg in progress_messages:
            clear_line()
            cprint(f" {msg} ", "black", "on_white")
            time.sleep(0.7)  # Show each message briefly
            animate_loading(1, f"{msg}", emoji)
        
        # Get model from factory
        model = model_factory.get_model(model_config["type"], model_config["name"])
        if not model:
            cprint(f"❌ Could not initialize {model_config['type']} model!", "white", "on_red")
            return None
        
        # 🆕 SELECT RANDOM STRATEGY TYPE
        if not strategy_type:
            strategy_type = random.choice(STRATEGY_TYPES)
        
        cprint(f"🎯 Strategy Type: {strategy_type['name']}", "magenta")
        
        # 🌍 Fetch live market context via MCP (now optimized!)
        market_context = get_market_context()
        
        # 🎯 Build COMPACT prompt with strategy type guidance
        strategy_guidance = f"\n\nSTRATEGY TYPE: {strategy_type['name']}\n"
        strategy_guidance += f"Focus: {strategy_type.get('focus', 'general trading')}\n"
        
        if 'timeframes' in strategy_type:
            strategy_guidance += f"Use timeframe: {random.choice(strategy_type['timeframes'])}\n"
        elif 'primary_tfs' in strategy_type and 'informative_tfs' in strategy_type:
            primary = random.choice(strategy_type['primary_tfs'])
            informative = random.choice(strategy_type['informative_tfs'])
            strategy_guidance += f"Primary TF: {primary}, Informative TF: {informative}\n"
        
        # Build COMPACT enhanced prompt
        if market_context:
            enhanced_prompt = (
                IDEA_GENERATION_PROMPT
                + strategy_guidance
                + "\n=== MARKET CONTEXT (max " + str(MAX_CONTEXT_CHARS) + " chars) ===\n"
                + market_context  # Now optimized & short!
                + "\n\nCreate strategy based on this context."
            )
        else:
            enhanced_prompt = IDEA_GENERATION_PROMPT + strategy_guidance
        
        # Show generation in progress message
        cprint(f"\n⏳ GENERATING TRADING STRATEGY IDEA...", "black", "on_white")
        time.sleep(0.5)  # Pause for readability
        
        # Generate response with enhanced prompt
        response = model.generate_response(
            system_prompt=enhanced_prompt,
            user_content="Generate one unique trading strategy idea based on the current market context.",
            temperature=0.8  # Higher temperature for more creativity
        )
        
        # Handle different response types
        if isinstance(response, str):
            idea = response
        elif hasattr(response, 'content'):
            idea = response.content
        else:
            idea = str(response)
        
        # Clean up the idea
        idea = clean_idea(idea)
        
        # Display the idea with animation - only once
        print()
        cprint("💡 TRADING STRATEGY IDEA GENERATED!", "white", "on_green")
        time.sleep(0.5)  # Pause for readability
        
        # Clear any previous output to avoid duplication
        clear_line()
        
        # Animate the idea text - only once
        animate_text(idea, "yellow", "on_blue")
        
        # Add some fun emojis
        print()
        for _ in range(2):
            position = random.randint(0, min(40, TERM_WIDTH-5))
            emoji = random.choice(EMOJIS)
            print(" " * position + emoji)
            time.sleep(0.3)
        
        return idea
        
    except Exception as e:
        cprint(f"❌ Error generating idea: {str(e)}", "white", "on_red")
        return None

def clean_idea(idea):
    """Clean up the generated idea text"""
    # Remove thinking tags if present (for DeepSeek-R1)
    if "<think>" in idea and "</think>" in idea:
        cprint("🧠 Detected thinking tags, cleaning...", "yellow")
        import re
        idea = re.sub(r'<think>.*?</think>', '', idea, flags=re.DOTALL).strip()
    
    # Extract content from markdown bold/quotes if present
    import re
    bold_match = re.search(r'\*\*"?(.*?)"?\*\*', idea)
    if bold_match:
        cprint("🔍 Extracting core idea from markdown formatting...", "yellow")
        idea = bold_match.group(1).strip()
    
    # Handle common prefixes from models
    prefixes_to_remove = [
        "Sure", "Sure,", "Here's", "Here is", "I'll", "I will", 
        "A unique", "One unique", "Here's a", "Here is a",
        "Trading strategy:", "Strategy idea:", "Trading idea:"
    ]
    
    for prefix in prefixes_to_remove:
        if idea.lower().startswith(prefix.lower()):
            idea = idea[len(prefix):].strip()
            # Remove any leading punctuation after prefix removal
            idea = idea.lstrip(',:;.- ')
    
    # Remove any markdown formatting
    idea = idea.replace('```', '').replace('#', '')
    
    # Remove any "Strategy:" or similar prefixes
    prefixes = ["Strategy:", "Idea:", "Trading Strategy:", "Trading Idea:"]
    for prefix in prefixes:
        if idea.startswith(prefix):
            idea = idea[len(prefix):].strip()
    
    # Remove quotes if they wrap the entire idea
    if (idea.startswith('"') and idea.endswith('"')) or (idea.startswith("'") and idea.endswith("'")):
        idea = idea[1:-1].strip()
    
    # Ensure it's a single line
    idea = ' '.join(idea.split())
    
    # Truncate if too long (aim for 1-2 sentences)
    sentences = re.split(r'[.!?]+', idea)
    if len(sentences) > 2:
        cprint("✂️ Truncating to first two sentences...", "yellow")
        idea = '.'.join(sentences[:2]).strip() + '.'
    
    # Ensure first letter is capitalized
    if idea and not idea[0].isupper():
        idea = idea[0].upper() + idea[1:]
    
    return idea

def log_idea(idea, model_config):
    """Log a new idea to both CSV and ideas.txt"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    model_name = f"{model_config['type']}-{model_config['name']}"
    
    # Animated saving sequence
    cprint("\n💾 SAVING IDEA TO DATABASE...", "white", "on_blue")
    time.sleep(0.5)  # Pause for readability
    
    # Animate moon phases - simplified
    for phase in MOON_PHASES:
        clear_line()
        print(f"\r{colored(' ' + phase + ' Saving to Moon Dev database... ', 'white', 'on_magenta')}", end="", flush=True)
        time.sleep(0.3)  # Slower animation
    print()
    
    # Log to CSV
    with open(IDEAS_CSV, 'a', newline='') as f:
        writer = csv.writer(f)
        writer.writerow([timestamp, model_name, idea])
    
    # Check if ideas.txt ends with a newline
    needs_newline = False
    if IDEAS_TXT.exists():
        with open(IDEAS_TXT, 'r') as f:
            content = f.read()
            if content and not content.endswith('\n'):
                needs_newline = True
    
    # Append to ideas.txt
    with open(IDEAS_TXT, 'a') as f:
        if needs_newline:
            f.write(f"\n{idea}\n")
        else:
            f.write(f"{idea}\n")
    
    # Success message with animation
    time.sleep(0.5)  # Pause for readability
    cprint("✅ IDEA SAVED SUCCESSFULLY!", "white", "on_green")
    time.sleep(0.3)
    
    # Display save details with alternating colors
    cprint(f"📊 CSV entry: {timestamp}", "black", "on_white")
    time.sleep(0.2)
    cprint(f"🤖 Model used: {model_name}", "white", "on_blue")
    time.sleep(0.2)
    cprint(f"📝 Added to ideas.txt", "white", "on_magenta")
    
    # Show the idea with a fancy border - ensure no duplication
    border = "★" * min(60, TERM_WIDTH)
    print("\n" + border)
    
    # Display the idea with a clean presentation
    clear_line()
    idea_display = f" 💡 {idea}"
    # Wrap long ideas
    if len(idea_display) > TERM_WIDTH - 4:
        wrapped_idea = textwrap.fill(idea_display, width=TERM_WIDTH - 4)
        cprint(wrapped_idea, "yellow", "on_blue")
    else:
        cprint(idea_display, "yellow", "on_blue")
    
    print(border + "\n")

def run_idea_generation_loop(interval=10):
    """Run the idea generation loop with a specified interval between generations"""
    setup_files()
    
    # Fancy startup animation
    animate_moon_dev()
    time.sleep(0.5)  # Pause for readability
    cprint("\n🌟 MOON DEV'S RESEARCH AGENT ACTIVATED! 🌟", "white", "on_magenta")
    time.sleep(0.5)  # Pause for readability
    cprint("🔄 Beginning continuous idea generation loop", "cyan")
    time.sleep(1)  # Pause for readability
    
    try:
        while True:
            # Load existing ideas to check for duplicates
            existing_ideas = load_existing_ideas()
            cprint(f"📚 Loaded {len(existing_ideas)} existing ideas for duplicate checking", "white", "on_blue")
            time.sleep(1)  # Pause for readability
            
            # Select a random model
            model_config = random.choice(MODELS)
            
            # Generate idea
            idea = generate_idea(model_config)
            
            if idea:
                # Check if it's a duplicate
                if is_duplicate(idea, existing_ideas):
                    cprint(f"🔄 DUPLICATE DETECTED!", "white", "on_red")
                    cprint(f"Skipping: {idea}", "yellow")
                else:
                    # Log the new idea
                    log_idea(idea, model_config)
            
            # Fun waiting animation - exactly 10 seconds
            cprint(f"\n⏱️ COOLDOWN PERIOD ACTIVATED", "white", "on_blue")
            time.sleep(0.5)  # Pause for readability
            
            # Show a colorful countdown - simplified for terminal
            moon_emojis = ["🌑", "🌒", "🌓", "🌔", "🌕", "🌖", "🌗", "🌘"]
            bg_colors = ["on_blue", "on_magenta", "on_cyan", "on_green"]
            
            for i in range(10):  # Always exactly 10 seconds
                # Cycle through emojis and backgrounds
                emoji = moon_emojis[i % len(moon_emojis)]
                bg = bg_colors[i % len(bg_colors)]
                
                # Display countdown with simple animation
                remaining = 10 - i
                clear_line()
                print(f"\r{colored(f' {emoji} Next idea in: {remaining} seconds ', 'white', bg)}", end="", flush=True)
                time.sleep(1)
            
            clear_line()
            print("\n" + "=" * min(60, TERM_WIDTH))
            
    except KeyboardInterrupt:
        cprint("\n👋 MOON DEV'S RESEARCH AGENT SHUTTING DOWN...", "white", "on_yellow")
        
        # Shutdown animation
        for i in range(5):
            print(f"\r{'.' * i}", end="", flush=True)
            time.sleep(0.3)
        
        cprint("\n🌙 Thank you for using Moon Dev's Research Agent! 🌙", "white", "on_magenta")
    except Exception as e:
        cprint(f"\n❌ FATAL ERROR: {str(e)}", "white", "on_red")
        import traceback
        cprint(traceback.format_exc(), "red")

def test_run(num_ideas=1, interval=10):
    """Run a short test of the idea generation process"""
    setup_files()
    
    # Fancy startup animation
    animate_moon_dev()
    time.sleep(0.5)  # Pause for readability
    cprint("\n🧪 MOON DEV'S RESEARCH AGENT - TEST MODE", "white", "on_magenta")
    time.sleep(0.5)  # Pause for readability
    cprint(f"🔄 Will generate {num_ideas} ideas with {interval} seconds interval", "cyan")
    time.sleep(1)  # Pause for readability
    
    try:
        existing_ideas = load_existing_ideas()
        cprint(f"📚 Loaded {len(existing_ideas)} existing ideas for duplicate checking", "white", "on_blue")
        time.sleep(1)  # Pause for readability
        
        ideas_generated = 0
        while ideas_generated < num_ideas:
            # Select a random model
            model_config = random.choice(MODELS)
            
            # Generate idea
            idea = generate_idea(model_config)
            
            if idea:
                # Check if it's a duplicate
                if is_duplicate(idea, existing_ideas):
                    cprint(f"🔄 DUPLICATE DETECTED!", "white", "on_red")
                    cprint(f"Skipping: {idea}", "yellow")
                else:
                    # Log the new idea
                    log_idea(idea, model_config)
                    ideas_generated += 1
                    existing_ideas.add(idea.lower())
            
            if ideas_generated < num_ideas:
                # Fun waiting animation - always 10 seconds
                cprint(f"\n⏱️ COOLDOWN PERIOD ACTIVATED", "white", "on_blue")
                time.sleep(0.5)  # Pause for readability
                
                # Show a colorful countdown - simplified for terminal
                moon_emojis = ["🌑", "🌒", "🌓", "🌔", "🌕", "🌖", "🌗", "🌘"]
                bg_colors = ["on_blue", "on_magenta", "on_cyan", "on_green"]
                
                # Always use exactly 10 seconds regardless of the interval parameter
                for i in range(10):
                    # Cycle through emojis and backgrounds
                    emoji = moon_emojis[i % len(moon_emojis)]
                    bg = bg_colors[i % len(bg_colors)]
                    
                    # Display countdown with simple animation
                    remaining = 10 - i
                    clear_line()
                    print(f"\r{colored(f' {emoji} Next idea in: {remaining} seconds ', 'white', bg)}", end="", flush=True)
                    time.sleep(1)
                
                clear_line()
                print()
        
        # Success animation
        cprint(f"\n✅ TEST COMPLETED SUCCESSFULLY!", "white", "on_green")
        time.sleep(0.5)  # Pause for readability
        cprint(f"Generated {ideas_generated} ideas", "yellow")
        
        # Show some celebratory emojis
        for _ in range(5):
            position = random.randint(0, min(40, TERM_WIDTH-5))
            emoji = random.choice(EMOJIS)
            print(" " * position + emoji)
            time.sleep(0.3)
        
    except KeyboardInterrupt:
        cprint("\n👋 Test interrupted", "white", "on_yellow")
    except Exception as e:
        cprint(f"\n❌ ERROR DURING TEST: {str(e)}", "white", "on_red")
        import traceback
        cprint(traceback.format_exc(), "red")

def main():
    """Main function to run the research agent"""
    # Check if we're running in test mode
    if len(sys.argv) > 1 and sys.argv[1] == "--test":
        test_run()
    else:
        run_idea_generation_loop()

if __name__ == "__main__":
    main()