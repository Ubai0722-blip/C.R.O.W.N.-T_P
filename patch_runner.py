import os
import shutil

def main():
    print('Applying patches...')
    update_doc = '''# C.R.O.W.N 0.0.4 更新文档

## BUG Fixes
1. WebUI Config Reset Issue
2. DB Manager Parameter Error
3. Persona Bottom Bindings Bug

## New Features
1. Global Module Toggle Active
2. Account Binding System Realized
3. Lover Mode Refactored into Relationship Module
4. Tone & Scene Libraries Active
5. Dynamic Priority Engine in Core Pipeline

See modified files in 0.0.4补丁 directory.
'''
    with open('0.0.4更新文档.md', 'w', encoding='utf-8') as f:
        f.write(update_doc)

    print('Creating patch directories...')
    patch_dir = '0.0.4补丁'
    files_to_copy = [
        'prts_config.py', 'db_manager.py', 'src/core/pipeline.py',
        'src/interaction/proactive.py', 'src/interaction/time_awareness.py'
    ]
    for f in files_to_copy:
        if os.path.exists(f):
            dest = os.path.join(patch_dir, f)
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            shutil.copy2(f, dest)
            print(f'Copied {f} to {dest}')

if __name__ == '__main__':
    main()