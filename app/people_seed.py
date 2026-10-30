"""EPEC people from the org chart held in the epec-knowledge-base skill: the 17/08/26 chart as changed by the 21/10/2026 re-organisation memo.
Each entry is (name, business title as the chart gives it or None, reports to, group, options). Options: ecf = an ECF role key taken from a grade word on the chart
("Principal", "Senior", "Graduate", "Cadet" in a team list) where the chart gives no business title; engagement; status (serving notice).
Only what the chart states is recorded: no ECF level of an individual, no PM level, no contact details. The chart has not been redrawn since 21/10/2026 and the
interim reporting lines of Finance, Legal, IT, HSE and People & Culture are not stated, so those people have no reporting line here. People who have left are not loaded.
"""
S = []


def add(name, title=None, reports=None, group=None, **o):
    S.append((name, title, reports, group, o))


# ---- Board, executive and corporate leaders --------------------------------------------------------------------------------------
add("Jayne Whitney", "Chair of the Board", None, "Board")
add("Jamie Alonso", "Chief Operating Officer", None, "Executive")
add("Brayden Leisemann", "General Counsel", None, "Legal, Risk and Compliance")
add("May Ennis", "Head of Finance", None, "Finance")
add("Ryan Rickard", "General Manager – Engineering", "Jamie Alonso", "Engineering")
add("Jason Maloney", "Head of Delivery", None, "Projects")
add("Vinko Kovacevic", "General Manager – Strategic Growth", "Jamie Alonso", "Strategic Growth")
add("Calman Steindl", "Special Projects Lead", "Jamie Alonso", "Executive")
add("Joe Ling", "Strategic Sourcing Manager", "Jamie Alonso", "Executive")
add("Isaac McFadzean", "Procurement Manager", "Jamie Alonso", "Executive")

# ---- Engineering (Ryan Rickard) ------------------------------------------------------------------------------------------------------
add("Mick Flynn", "Head of Engineering", "Ryan Rickard", "Engineering")
add("Gareth Byrne", "Head of Technology", "Ryan Rickard", "Technology")
add("Paddy O'Connell", "Head of Commissioning", "Ryan Rickard", "Commissioning")
add("Nadali Mahmoudi", "Technical Director – Electricity Market & Network Modelling", "Ryan Rickard", "Modelling")
add("Jarek Krata", "Head of Technical", "Ryan Rickard", "Technical")
for n, g, e in [("Nick Linwood", 1, "principal"), ("Luciano Roco", 1, "sr_eng"), ("Keven Tie", 1, None), ("Ali Mahmoudian", 1, None), ("Moutushi (Monty) Mazumder", 1, None), ("Jack (Bolong) Zhang", 1, "grad_eng"),
                ("Tim Stewart", 2, "principal"), ("Riley Canning", 2, "grad_eng"),
                ("James Naughton", 3, "principal"), ("Jalil Yaghoobi", 3, "sr_eng"), ("Meghdad Tourandaz Kenari", 3, None), ("Afsar Ali Shaikh", 3, None), ("Tu Phan", 3, None), ("Piran Lombard", 3, "grad_eng"), ("Jasdeep Renny", 3, "cadet_eng"),
                ("Franco Perez", 4, "principal"), ("Ishitha (Ishi) Lokukaluge", 4, None), ("Karize De La Cruz", 4, None), ("Jiahui (Jovie) Zhang", 4, "grad_eng"), ("Ahmed Badat", 4, "grad_eng"),
                ("Razibul Islam", 5, "principal"), ("Imtiaz Madni", 5, None), ("Sharmin Rahman", 5, None), ("Morshed Alam", 5, None), ("Rabiul Islam", 5, None), ("Behnam Hashemian", 5, None), ("Sahar Nezhad", 5, "grad_eng"),
                ("Behzad Hajmo", 6, "principal")]:
    add(n, None, "Mick Flynn", f"Engineering team {g}", **({"ecf": e} if e else {}))
add("Dan Brophy", "Senior Design Engineer", "Mick Flynn", "Engineering team 2")
add("Luisa Lopez", "Program Manager", "Mick Flynn", "Engineering support")
add("Lesley Christie", "Senior Project Administrator", "Mick Flynn", "Engineering support")
add("Reyna Hartnett", "Project Administrator", "Mick Flynn", "Engineering support")
add("Ayushi Modh", "Bid Coordinator", "Mick Flynn", "Engineering support")
add("Simon Willis", "Technical Director", "Gareth Byrne", "Technology")
for n in ("Jithin Rajan", "Nicolaus Van Shie", "Miquel Gabalda Galcera"):
    add(n, "Senior Product Engineer", "Simon Willis", "Technology")
add("Jun Su", None, "Simon Willis", "Technology", ecf="grad_eng")
add("Rohan Ghanwar", None, "Simon Willis", "Technology", ecf="cadet_eng")
add("Maria Miranda", None, "Simon Willis", "Technology", ecf="cadet_eng")
add("Marty Johnson", "Senior Power Systems Engineer", "Gareth Byrne", "Technology (HIL)")
add("Rasel Mahmud", "Power Systems Engineer", "Gareth Byrne", "Technology (HIL)")
add("George Aspros", "Commissioning Specialist", "Paddy O'Connell", "Commissioning", engagement="contractor")
add("Rebecca Eager", "Electrical Engineer", "Paddy O'Connell", "Commissioning")
add("Pasindu Ambegoda", "Graduate Electrical Engineer", "Paddy O'Connell", "Commissioning", ecf="grad_eng")
add("Nico Schwetje", "Renewable Engineering Specialist", "Paddy O'Connell", "Commissioning")
add("Rodrigo Ghersi Tupper", "Senior Electrical Engineer", "Paddy O'Connell", "Commissioning")
add("Tom Groth", "Electrical Engineer", "Paddy O'Connell", "Commissioning")
add("Paul Bandarian", None, "Nadali Mahmoudi", "Modelling", ecf="sr_modeller")
add("Pruthivi Rajan", None, "Nadali Mahmoudi", "Modelling")
add("Liam Atkinson", None, "Nadali Mahmoudi", "Modelling")
add("Guoyang (Kevin) Luo", None, "Nadali Mahmoudi", "Modelling", ecf="grad_modeller")
add("Felix Pountney", None, "Nadali Mahmoudi", "Modelling", ecf="cadet_modeller")
add("Bobby Heyer", None, "Nadali Mahmoudi", "Modelling", ecf="principal_modeller")
add("Negar Saebi", None, "Nadali Mahmoudi", "Modelling")
add("Advaith Suresh", None, "Nadali Mahmoudi", "Modelling")
add("Kevin Au-Duong", "Software Engineer", "Nadali Mahmoudi", "Modelling")
add("Charles Robinson", None, "Nadali Mahmoudi", "Modelling", ecf="cadet_modeller")
add("Tristan Panquet", "Intern", "Jarek Krata", "Technical")

# ---- Projects ---------------------------------------------------------------------------------------------------------------------
add("Peter Little", "Project Director", "Jason Maloney", "Projects")
add("Ben Thomson", "Project Director", "Jason Maloney", "Projects")
add("Matt O'Connor", "Operations Manager – Projects", "Jason Maloney", "Projects")
add("Mark Jennings", "Field Services Superintendent", "Jason Maloney", "Projects")
add("Praveen Atmuri", "SCADA & Controls Manager", "Jason Maloney", "Projects")
add("Phil Gold", "Design Manager", "Jason Maloney", "Design", status="serving notice")
add("Tim Duff", "Substation Commissioning Manager", "Jason Maloney", "Commissioning")
for n, t in [("Sertac Kamil", "Senior Project Manager"), ("Jake Notley", "Project Manager"), ("Vincent Dewulf", "Project Manager"), ("Shelby Fraser", "Senior Project Administrator"),
             ("Damon Isaacs", "Project Coordinator"), ("Leone Tesimale", "Project Administrator")]:
    add(n, t, "Peter Little", "Projects: Peter Little's team")
for n, t in [("Amy Ellingworth", "Project Manager"), ("Johanie Botha", "Project Manager"), ("Brad Fallis", "Senior Project Manager"), ("Morgan Branson", "Project Coordinator"),
             ("Tina Robinson", "Senior Project Administrator"), ("Christy Bulos", "Document Controller"), ("Pariya Mousavi", "Scheduler"), ("Corallee Malcolm", "Project Administrator (Site)")]:
    add(n, t, "Ben Thomson", "Projects: Ben Thomson's team")
for n, t in [("Grant Colley", "Construction Manager"), ("Mark Hardie", "Construction Manager"), ("Ricky Hardy", None), ("Stephen Healey", "Site Supervisor – Electrical"), ("John Nixon", "Site Supervisor – Electrical"),
             ("Jamie Anderson", "Electrician"), ("Liam Dickens", "Apprentice"), ("Hayden Maloney", "Apprentice")]:
    add(n, t, "Matt O'Connor", "Operations")
for n, t in [("Sebastian Huch", "Warehouse Supervisor"), ("Clifford Williams", "Storeperson"), ("Seani Dennis", "Operations Support Officer")]:
    add(n, t, "Mark Jennings", "Field services")
for lead, members in [("Tysan Greaves", [("Grayson Hughes", None), ("Tim Gardiner", None), ("Alex Godfrey", None), ("Ethan Isaacs", "cadet_eng")]),
                      ("Ana Prado", [("Brian Cortes", None), ("Victor Salomao", None), ("Corey Singleton", None), ("Conor Sheehy", "cadet_eng")]),
                      ("Genesis Nolledo", [("Fuad Ali", None), ("Oscar Stott", None), ("Pasindu Herriarachchi", "grad_eng"), ("Lochlan Ruhl", "cadet_eng")])]:
    add(lead, "Senior SCADA Engineer", "Praveen Atmuri", "SCADA & Controls")
    for n, e in members:
        add(n, None, lead, "SCADA & Controls", **({"ecf": e} if e else {}))
add("Dennis Miranda", "Program Manager", "Praveen Atmuri", "SCADA & Controls")
add("Renan Almada Melo", "SCADA Drafter", "Dennis Miranda", "SCADA & Controls")
add("Sam Veysi Raygani", "Principal Engineer", "Phil Gold", "Design")
add("William Enwereonu", "Design Engineer", "Sam Veysi Raygani", "Design")
add("Mohammad Behraftar", "Design Engineer", "Sam Veysi Raygani", "Design")
add("Harry Marles", None, "Sam Veysi Raygani", "Design")
add("Camilo Cortes Adarme", "Senior Project Engineer", "Phil Gold", "Design")
for n in ("Cameron Stabler", "Larissa Oliveira", "Res Ale", "Juan Viana Sierra", "Marchel Van Schalkwyk", "Nabin Khatri"):
    add(n, "Project Engineer", "Camilo Cortes Adarme", "Design")
add("Geoff Hampton", "Senior Designer", "Phil Gold", "Design")
add("Giovanna Bonato Renato", "Substation Civil Designer", "Geoff Hampton", "Design")
for n in ("Megan Hemmati", "Renata Noguchi", "Felipe Vargas"):
    add(n, "Drafter", "Geoff Hampton", "Design")
add("Carlos Avila Rojas", "Senior Designer", "Phil Gold", "Design")
add("Anna Teixeira Botti", "Substation Civil Designer", "Carlos Avila Rojas", "Design")
add("Julian Mendez Mendoza", "Drafter", "Carlos Avila Rojas", "Design")
add("Peter Hogan", "Substation Principal Engineer", "Phil Gold", "Design")
add("Angaline Krishna", "Substation Design Engineer", "Peter Hogan", "Design")
add("Ian McKee", "Substation Design Engineer", "Peter Hogan", "Design")
add("Daniel Fisher", "Cadet Engineer", "Peter Hogan", "Design")
add("Connor Purvey", "Cadet Engineer", "Peter Hogan", "Design")
add("Elliott Parker", "Design Engineer", "Peter Hogan", "Design", engagement="secondment")
add("Laura Sanchez", "Design Support Administrator", "Phil Gold", "Design")
add("Ian Jordaan", "Substation Commissioning Lead", "Tim Duff", "Commissioning", status="serving notice")
add("Neel Baapana", "Senior Commissioning Engineer", "Ian Jordaan", "Commissioning")
add("Jesus Habulan", "Commissioning Engineer", "Ian Jordaan", "Commissioning")
add("Neville Palmer", "Projects Commissioning Lead", "Tim Duff", "Commissioning")
add("Rohit Yogi", "Electrical Engineer", "Neville Palmer", "Commissioning")

# ---- Finance, legal, strategic growth and support services (interim reporting lines not stated) -----------------------------------------------
add("Phil Airey", "Financial Controller", "May Ennis", "Finance")
add("Clare Balman", "Cost Control Manager", "May Ennis", "Finance")
for n, t in [("Jenna Druery", "Finance Officer"), ("Deborah Pattison", "Finance Officer AP/AR"), ("Bhakti Dave", "Finance Officer")]:
    add(n, t, "Clare Balman", "Finance")
add("Ginia Matos Gonzalez", "Senior Accountant", "May Ennis", "Finance")
add("Shauna Westwood", "Payroll Officer", "May Ennis", "Finance")
add("Jordan Mott", "Commercial Manager", "Brayden Leisemann", "Legal, Risk and Compliance")
add("David Thomas", "Contracts Manager", "Brayden Leisemann", "Legal, Risk and Compliance")
add("Sharon Sangha", "Contracts Administrator", "David Thomas", "Legal, Risk and Compliance")
add("Suey Saikaew", "Contracts Administrator", "David Thomas", "Legal, Risk and Compliance")
add("Ryan Carr", "Director, New Projects", "Vinko Kovacevic", "Strategic Growth")
add("Matt Robinson", "Project Development Manager", "Ryan Carr", "Strategic Growth")
add("Michael Walton", "Lead Estimator", "Ryan Carr", "Strategic Growth")
add("Romy Bridgeman", "Junior Estimator", "Michael Walton", "Strategic Growth")
add("Charlotte Little", "Marketing and Communication Coordinator", "Vinko Kovacevic", "Strategic Growth")
add("Roksana Hasheminejad", "Marketing Content Creator", "Vinko Kovacevic", "Strategic Growth")
add("Nastasia Belz", "Strategic Growth Coordinator", "Vinko Kovacevic", "Strategic Growth")
add("Peter Allen", "HSEQ Manager", None, "HSE")
add("Ken Patterson", "HSE Specialist", "Peter Allen", "HSE")
add("Brad Lilley", "HSE Project Lead", "Peter Allen", "HSE")
add("Richard Marsom", "HSE Advisor", "Peter Allen", "HSE")
add("Paul Riley", "HSE Advisor", "Peter Allen", "HSE")
add("Rita Ames", "HSEQ Administrator", "Peter Allen", "HSE")
add("Eleanor Keast", "Receptionist", None, "Support services")
add("Kayla McCormack", "F&B Attendant", "Eleanor Keast", "Support services")
add("Sophia Fiala", "Business Support Attendant", "Eleanor Keast", "Support services")
add("Rosie Galloway", "Employee and Industrial Relations Lead", None, "People & Culture")
add("William Hobbs", "People and Culture Lead", None, "People & Culture")
add("Olivia Baker", "People and Culture Coordinator", "William Hobbs", "People & Culture")
add("Priyanka Gupta", "Talent Advisor", "William Hobbs", "People & Culture")
add("Josh Martini", "IT Manager", None, "IT")
add("Sam Sheldon", "Executive Assistant, Engineering", "Ryan Rickard", "Engineering")

SOURCE = "EPEC org chart 17/08/26 with the 21/10/2026 re-organisation (epec-knowledge-base skill)"
