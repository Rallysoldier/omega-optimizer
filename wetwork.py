import psutil 

def find_pid_by_name(name: int) -> None:
    for p in psutil.process_iter(['pid','name','exe','create_time']): 
        try: 
            if (p.info['name'] or '').lower().startswith(name): 
                print(p.info) 
        except psutil.NoSuchProcess: 
            pass

def find_unique_pid_names(print_info=None) -> list[str]:
    unique_process_names = []
    for p in psutil.process_iter(['pid','name','exe','create_time']): 
        try: 
            if p.info['name'] not in unique_process_names:
                unique_process_names.append(p.info['name'])
                if print_info:
                    print(p.info) 
        except psutil.NoSuchProcess: 
            pass
    return unique_process_names

names = find_unique_pid_names()
names.sort(key=str.lower)

print("================ PID NAMES ================")
for name in names:
    print(name)
