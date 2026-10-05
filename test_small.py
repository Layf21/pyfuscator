def check_password__obf(p):
    return p == "foobar"

password__obf = input("Enter the password: ")

if check_password__obf(password__obf):
    print("Correct.")
else:
    print("Wrong.")
