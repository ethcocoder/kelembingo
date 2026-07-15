import re

with open('dashboard/index.html', 'r', encoding='utf-8') as f:
    text = f.read()

# 1. Remove prediction nav item
nav_item_pattern = r'<a class="nav-item[^>]*data-section="prediction"[^>]*>.*?</a>'
text = re.sub(nav_item_pattern, '', text, flags=re.DOTALL)

# 2. Remove Prediction Section completely
pred_section_pattern = r'<!-- ==================== PREDICTION CONTROL SECTION ==================== -->.*?</div>\s*</div>\s*</div>\s*(?=<!-- ==================== REPORTS SECTION ====================)'
text = re.sub(pred_section_pattern, '', text, flags=re.DOTALL)

# 3. Remove prediction JS functions completely
pred_js_pattern = r'// ==================== PREDICTION CONTROL ====================.*?(?=// ==================== REPORTS ====================)'
text = re.sub(pred_js_pattern, '', text, flags=re.DOTALL)

# 4. Remove Clear All cartelas button
clear_btn_pattern = r'<button onclick="deleteAllCartelas\(\)"[^>]*>Clear All</button>'
text = re.sub(clear_btn_pattern, '', text)

# 5. Remove cartelas JS functions
js_funcs = r'function deleteCartela\(id\).*?function confirmClearAllCartelas\(\) \{.*?\}\s*'
text = re.sub(js_funcs, '', text, flags=re.DOTALL)

with open('dashboard/index.html', 'w', encoding='utf-8') as f:
    f.write(text)
