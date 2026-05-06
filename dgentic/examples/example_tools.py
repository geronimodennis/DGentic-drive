"""Example tools that can be created and used in DGentic."""

# Example 1: JSON Parser Tool
json_parser_tool = '''
import json
import sys

def parse_json(json_string):
    """Parse JSON string and return Python object."""
    try:
        result = json.loads(json_string)
        return {
            "success": True,
            "result": result,
            "type": type(result).__name__
        }
    except json.JSONDecodeError as e:
        return {
            "success": False,
            "error": str(e),
            "error_line": e.lineno,
            "error_column": e.colno
        }

# Main execution
if __name__ == "__main__":
    # Example usage
    test_json = \'{"name": "test", "values": [1, 2, 3]}\'
    result = parse_json(test_json)
    print(result)
'''

# Example 2: Markdown to HTML Converter
markdown_converter_tool = '''
import re

def markdown_to_html(markdown_text):
    """Convert basic markdown to HTML."""
    html = markdown_text
    
    # Headers
    html = re.sub(r'^### (.*?)$', r'<h3>\\1</h3>', html, flags=re.MULTILINE)
    html = re.sub(r'^## (.*?)$', r'<h2>\\1</h2>', html, flags=re.MULTILINE)
    html = re.sub(r'^# (.*?)$', r'<h1>\\1</h1>', html, flags=re.MULTILINE)
    
    # Bold and italic
    html = re.sub(r'\\*\\*(.*?)\\*\\*', r'<b>\\1</b>', html)
    html = re.sub(r'\\*(.*?)\\*', r'<i>\\1</i>', html)
    
    # Lists
    html = re.sub(r'^\\- (.*?)$', r'<li>\\1</li>', html, flags=re.MULTILINE)
    
    # Paragraphs
    html = re.sub(r'\\n\\n', '</p><p>', html)
    html = '<p>' + html + '</p>'
    
    return {
        "success": True,
        "html": html,
        "character_count": len(html)
    }

# Main execution
if __name__ == "__main__":
    md = "# Title\\n\\nThis is **bold** text.\\n\\n- Item 1\\n- Item 2"
    result = markdown_to_html(md)
    print(result)
'''

# Example 3: Data Validator Tool
data_validator_tool = '''
def validate_data(data_dict, schema):
    """Validate data against a schema."""
    errors = []
    
    for key, expected_type in schema.items():
        if key not in data_dict:
            errors.append(f"Missing required field: {key}")
        elif not isinstance(data_dict[key], expected_type):
            errors.append(
                f"Field {key}: expected {expected_type.__name__}, "
                f"got {type(data_dict[key]).__name__}"
            )
    
    return {
        "valid": len(errors) == 0,
        "errors": errors,
        "error_count": len(errors)
    }

# Main execution
if __name__ == "__main__":
    schema = {"name": str, "age": int, "email": str}
    data = {"name": "John", "age": 30, "email": "john@example.com"}
    result = validate_data(data, schema)
    print(result)
'''

# Example 4: Text Statistics Tool
text_stats_tool = '''
import re

def analyze_text(text):
    """Analyze text and return statistics."""
    words = text.split()
    sentences = re.split(r'[.!?]+', text)
    
    return {
        "character_count": len(text),
        "word_count": len(words),
        "sentence_count": len([s for s in sentences if s.strip()]),
        "average_word_length": sum(len(w) for w in words) / len(words) if words else 0,
        "unique_words": len(set(words)),
    }

# Main execution
if __name__ == "__main__":
    text = "This is a sample text. It has multiple sentences. Each one is important."
    result = analyze_text(text)
    print(result)
'''

# Example 5: CSV Processor Tool
csv_processor_tool = '''
import csv
import io

def process_csv(csv_data, operation="stats"):
    """Process CSV data."""
    try:
        reader = csv.DictReader(io.StringIO(csv_data))
        rows = list(reader)
        
        if operation == "stats":
            return {
                "success": True,
                "row_count": len(rows),
                "column_count": len(rows[0]) if rows else 0,
                "columns": list(rows[0].keys()) if rows else [],
                "sample": rows[0] if rows else None
            }
        
        elif operation == "count":
            return {
                "success": True,
                "total_rows": len(rows)
            }
        
        else:
            return {
                "success": False,
                "error": f"Unknown operation: {operation}"
            }
    
    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }

# Main execution
if __name__ == "__main__":
    csv_data = "name,age,city\\nJohn,30,NYC\\nJane,25,LA"
    result = process_csv(csv_data, "stats")
    print(result)
'''

tools = {
    "json_parser": {
        "name": "json_parser",
        "description": "Parse JSON strings and validate their structure",
        "code": json_parser_tool,
    },
    "markdown_converter": {
        "name": "markdown_converter",
        "description": "Convert Markdown text to HTML",
        "code": markdown_converter_tool,
    },
    "data_validator": {
        "name": "data_validator",
        "description": "Validate data against a schema",
        "code": data_validator_tool,
    },
    "text_stats": {
        "name": "text_stats",
        "description": "Analyze text and compute statistics",
        "code": text_stats_tool,
    },
    "csv_processor": {
        "name": "csv_processor",
        "description": "Process and analyze CSV data",
        "code": csv_processor_tool,
    },
}


def get_tool(tool_name: str):
    """Get a tool by name."""
    return tools.get(tool_name)


def list_tools():
    """List all available example tools."""
    return list(tools.keys())


if __name__ == "__main__":
    print("Available Example Tools:")
    for name in list_tools():
        tool = get_tool(name)
        print(f"  - {tool['name']}: {tool['description']}")
