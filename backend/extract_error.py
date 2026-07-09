import re

log_path = r"C:\Users\Nayan Patel\.gemini\antigravity-ide\brain\9b4f9b57-d5d3-41dd-993d-246c459891a9\.system_generated\tasks\task-155.log"
with open(log_path, 'r', encoding='utf-8') as f:
    content = f.read()

# search for "Exception Type:" and "Exception Value:"
type_match = re.search(r'<th>Exception Type:</th>\s*<td>([^<]+)</td>', content)
val_match = re.search(r'<th>Exception Value:</th>\s*<td><pre>([^<]+)</pre></td>', content)

if type_match:
    print("Exception Type:", type_match.group(1).strip())
if val_match:
    print("Exception Value:", val_match.group(1).strip())
    
# Or just search for the title
title = re.search(r'<title>([^<]+)</title>', content)
if title:
    print("Title:", title.group(1).strip())
