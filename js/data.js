// data.js
// Static recipe pool and dish-illustration library that Racik's AI generation
// would normally return. In this prototype it's a representative fixed sample
// so the planning UI has real content to render and edit.

export const recipePool = [
    { main:'Sweet Soy-Glazed Grilled Chicken', mainCat:'Main dish', mainImg:'🍗', mainRegion:'Mangut',
      side:'Stir-Fried Spinach & Corn (Sayur Bening Bayam Jagung)', sideCat:'Vegetable', sideImg:'🥬', sideRegion:'Jawa',
      staple:'Steamed Rice', stapleImg:'🍚', stapleRegion:'Solo',
      fruit:'Salak Pondoh', fruitRegion:'Sleman / Bali',
      extra:'', 
      cost:1140000, tag:'Regional favorite',
      kcal:395, protein:26, fat:14, adequacy:88,
      slotCost:{ veg:1296, main:3087, fruit:1555, staple:1523, extra:0 },
      why:[ 'Tagged to West Java in the recipe corpus', 'Meets 88% of the daily protein target for this age group', 'Within 3% of the per-portion budget' ],
      mainIngredients:[['Chicken pieces','18 kg'],['Sweet soy sauce','1.5 L'],['Shallots','2 kg'],['Garlic','1 kg'],['Red chili','800 g'],['Cooking oil','1.2 L']],
      mainSteps:['Coat chicken with the ground spice mix, let it rest for 20 minutes.','Grill the chicken over coals until half cooked.','Brush with sweet soy sauce, grill again until fully cooked.','Serve with remaining soy glaze and fried shallots.'],
      mainNutrition:{ kcal:310, protein:24, fat:14 },
      sideIngredients:[['Water spinach','6 kg'],['White tofu','4 kg'],['Garlic','400 g'],['Shrimp paste','60 g']],
      sideSteps:['Stir-fry garlic and shrimp paste until fragrant.','Add tofu, cook briefly until lightly browned.','Add water spinach, stir quickly until wilted.','Season with salt and a pinch of sugar, then remove from heat.'],
      sideNutrition:{ kcal:85, fiber:3, iron:2.1 } },

    { main:'Fried Tilapia', mainCat:'Main dish', mainImg:'🐟', mainRegion:'Mangut',
      side:'Tamarind Vegetable Soup (Sayur Asem)', sideCat:'Vegetable', sideImg:'🥕', sideRegion:'Jawa',
      staple:'Steamed Rice', stapleImg:'🍚', stapleRegion:'Solo',
      fruit:'Watermelon', fruitRegion:'National',
      extra:'',
      cost:1080000, tag:'',
      kcal:340, protein:28, fat:12, adequacy:81,
      slotCost:{ veg:1180, main:2900, fruit:907, staple:1523, extra:0 },
      why:[ 'Freshwater fish priced well this week at the regional market', 'High protein, moderate cost — helps offset a richer day elsewhere', 'Commonly served in this province\'s school meal programmes' ],
      mainIngredients:[['Tilapia, whole',"20 kg"],['Turmeric','300 g'],['Garlic','800 g'],['Lime','1.5 kg'],['Cooking oil','1.5 L']],
      mainSteps:['Rub tilapia with turmeric, garlic and salt.','Let marinate for 15 minutes.','Deep-fry until golden and crisp.','Serve with fresh lime wedges.'],
      mainNutrition:{ kcal:265, protein:29, fat:11 },
      sideIngredients:[['Tamarind paste','500 g'],['Long beans','5 kg'],['Chayote','4 kg'],['Corn','3 kg'],['Peanuts','1 kg']],
      sideSteps:['Bring tamarind broth to a boil.','Add corn and chayote, simmer 8 minutes.','Add long beans and peanuts, cook until tender.','Season with salt and a little palm sugar.'],
      sideNutrition:{ kcal:75, fiber:4, iron:1.6 } },

    { main:'Beef Rendang', mainCat:'Main dish', mainImg:'🥘', mainRegion:'National dish',
      side:'Stir-Fried Green Beans', sideCat:'Vegetable', sideImg:'🫛', sideRegion:'Jawa',
      staple:'Steamed Rice', stapleImg:'🍚', stapleRegion:'Solo',
      fruit:'Banana', fruitRegion:'National',
      extra:'Boiled Egg',
      cost:1200000, tag:'Regional favorite',
      kcal:420, protein:30, fat:22, adequacy:92,
      slotCost:{ veg:1050, main:3800, fruit:820, staple:1523, extra:900 },
      why:[ 'National dish with very high local acceptance', 'Highest protein density in this week\'s rotation', 'Slightly above average cost — balanced by cheaper days' ],
      mainIngredients:[['Beef chuck','20 kg'],['Coconut milk','8 L'],['Shallots','2 kg'],['Galangal','500 g'],['Chili paste','1 kg']],
      mainSteps:['Sear beef chunks until browned on all sides.','Add ground spice paste, cook until fragrant.','Pour in coconut milk, simmer on low heat for 2.5 hours, stirring occasionally.','Cook until sauce reduces and darkens.'],
      mainNutrition:{ kcal:340, protein:28, fat:20 },
      sideIngredients:[['Green beans','6 kg'],['Garlic','300 g'],['Shallots','300 g'],['Chili','200 g']],
      sideSteps:['Stir-fry garlic and shallots until fragrant.','Add green beans, stir over high heat.','Season with salt and a little chili.','Cook until beans are just tender, then remove from heat.'],
      sideNutrition:{ kcal:80, fiber:3.5, iron:1.2 } },

    { main:'Sweet & Sour Tofu', mainCat:'Main dish', mainImg:'🍢', mainRegion:'Jawa',
      side:'Steamed Cassava Leaves', sideCat:'Vegetable', sideImg:'🥦', sideRegion:'Jawa Tengah',
      staple:'Steamed Rice', stapleImg:'🍚', stapleRegion:'Solo',
      fruit:'Papaya', fruitRegion:'National',
      extra:'',
      cost:860000, tag:'Budget pick',
      kcal:290, protein:18, fat:9, adequacy:74,
      slotCost:{ veg:980, main:2100, fruit:650, staple:1523, extra:0 },
      why:[ 'Plant-based protein keeps cost well under budget', 'Cassava leaves add iron and fiber missing earlier in the week', 'Lower protein day — paired with a protein-rich day after' ],
      mainIngredients:[['Firm tofu','16 kg'],['Pineapple','3 kg'],['Bell pepper','2 kg'],['Tomato sauce','1.5 L'],['Cornstarch','500 g']],
      mainSteps:['Pan-fry tofu cubes until golden on all sides.','Sauté bell pepper and pineapple briefly.','Add sweet-sour sauce, bring to a simmer.','Toss in tofu, thicken with cornstarch slurry.'],
      mainNutrition:{ kcal:230, protein:14, fat:9 },
      sideIngredients:[['Cassava leaves','7 kg'],['Garlic','300 g'],['Coconut milk','1 L'],['Anchovy paste','200 g']],
      sideSteps:['Boil cassava leaves until tender, then drain well.','Sauté garlic and anchovy paste until fragrant.','Add coconut milk and the boiled leaves.','Simmer briefly, season with salt.'],
      sideNutrition:{ kcal:95, fiber:5, iron:2.8 } },

    { main:'Chicken Soto Soup', mainCat:'Main dish', mainImg:'🍲', mainRegion:'Jawa Tengah',
      side:'Bean Sprout & Cabbage Salad', sideCat:'Vegetable', sideImg:'🥗', sideRegion:'Jawa',
      staple:'Steamed Rice', stapleImg:'🍚', stapleRegion:'Solo',
      fruit:'Orange', fruitRegion:'National',
      extra:'Krupuk',
      cost:990000, tag:'Regional favorite',
      kcal:360, protein:24, fat:13, adequacy:85,
      slotCost:{ veg:1100, main:2650, fruit:1100, staple:1523, extra:400 },
      why:[ 'Broth-based dish — easier to scale precisely for headcount', 'Well-liked comfort dish in this region', 'Balanced macro profile for a mid-week meal' ],
      mainIngredients:[['Chicken, whole','15 kg'],['Turmeric','250 g'],['Lemongrass','1 kg'],['Vermicelli','3 kg'],['Fried shallots','500 g']],
      mainSteps:['Simmer chicken with turmeric and aromatics until tender.','Shred the chicken, strain and season the broth.','Soak vermicelli in hot water until soft.','Assemble bowls with vermicelli, chicken and hot broth.'],
      mainNutrition:{ kcal:280, protein:22, fat:10 },
      sideIngredients:[['Bean sprouts','5 kg'],['Cabbage','4 kg'],['Lime','1 kg'],['Fried shallots','300 g']],
      sideSteps:['Blanch bean sprouts briefly, then cool in cold water.','Shred cabbage thinly.','Toss both with lime juice and a pinch of salt.','Top with fried shallots before serving.'],
      sideNutrition:{ kcal:60, fiber:3, iron:0.9 } },

    { main:'Grilled Fish in Banana Leaf', mainCat:'Main dish', mainImg:'🐠', mainRegion:'Sunda',
      side:'Sautéed Water Spinach', sideCat:'Vegetable', sideImg:'🥬', sideRegion:'Jawa',
      staple:'Steamed Rice', stapleImg:'🍚', stapleRegion:'Solo',
      fruit:'Guava', fruitRegion:'National',
      extra:'',
      cost:1050000, tag:'',
      kcal:350, protein:27, fat:12, adequacy:83,
      slotCost:{ veg:1050, main:3200, fruit:780, staple:1523, extra:0 },
      why:[ 'Banana-leaf steaming needs no added oil, keeping fat moderate', 'Coastal-style dish common to this province', 'Good protein-to-cost ratio for this budget tier' ],
      mainIngredients:[['Mackerel','18 kg'],['Turmeric paste','400 g'],['Banana leaf','40 sheets'],['Chili paste','600 g']],
      mainSteps:['Coat fish with turmeric and chili paste.','Wrap individually in banana leaf.','Grill over medium coals for 12–15 minutes per side.','Rest for 2 minutes before unwrapping and serving.'],
      mainNutrition:{ kcal:265, protein:26, fat:10 },
      sideIngredients:[['Water spinach','6 kg'],['Garlic','300 g'],['Chili','150 g'],['Cooking oil','300 ml']],
      sideSteps:['Heat oil, sauté garlic and chili until fragrant.','Add water spinach over high heat.','Stir quickly for about a minute.','Season with salt, remove promptly to keep it crisp.'],
      sideNutrition:{ kcal:70, fiber:2.8, iron:1.4 } },

    { main:'Beef & Potato Semur', mainCat:'Main dish', mainImg:'🍛', mainRegion:'Jawa',
      side:'Steamed Chayote', sideCat:'Vegetable', sideImg:'🥒', sideRegion:'Jawa',
      staple:'Steamed Rice', stapleImg:'🍚', stapleRegion:'Solo',
      fruit:'Rambutan', fruitRegion:'National',
      extra:'Tempeh Crisps',
      cost:1160000, tag:'Regional favorite',
      kcal:400, protein:25, fat:16, adequacy:87,
      slotCost:{ veg:900, main:3400, fruit:980, staple:1523, extra:650 },
      why:[ 'Sweet soy-based stew is a familiar home-style dish here', 'Potato adds carbohydrate variety alongside rice', 'On budget for a mid-week protein day' ],
      mainIngredients:[['Beef, cubed','18 kg'],['Potato','8 kg'],['Sweet soy sauce','2 L'],['Shallots','1.5 kg'],['Nutmeg','100 g']],
      mainSteps:['Brown beef cubes in a little oil.','Add shallots, garlic and nutmeg, cook until fragrant.','Add sweet soy sauce and water, simmer until beef is tender.','Add potato chunks, cook until soft.'],
      mainNutrition:{ kcal:320, protein:23, fat:14 },
      sideIngredients:[['Chayote','7 kg'],['Garlic','200 g'],['Salt','to taste']],
      sideSteps:['Peel and slice chayote into wedges.','Steam until just tender, about 10 minutes.','Toss with lightly fried garlic and salt.','Serve warm alongside the semur.'],
      sideNutrition:{ kcal:45, fiber:2, iron:0.5 } },
  ];

export const dayLabels = {
    M:'Monday', T1:'Tuesday', W:'Wednesday', T2:'Thursday', F:'Friday', S1:'Saturday', S2:'Sunday'
  };
export const weekdayOrder = ['M','T1','W','T2','F','S1','S2'];


  // Small flat-illustration library for dishes — consistent linework, warm palette,
  // used in place of emoji on the tray compartments and detail hero images.
export const dishArt = {
    grilledChicken: `<svg viewBox="0 0 100 100" fill="none" xmlns="http://www.w3.org/2000/svg">
      <ellipse cx="50" cy="78" rx="34" ry="6" fill="#1F2B22" opacity="0.08"/>
      <path d="M32 55 C28 40 38 24 52 24 C66 24 74 38 70 54 C68 62 62 70 55 74 L45 74 C38 70 34 63 32 55 Z" fill="#C0392B"/>
      <path d="M40 40 C42 34 48 30 54 31 C60 32 64 38 62 45" stroke="#7A2018" stroke-width="2.5" stroke-linecap="round"/>
      <path d="M38 50 L34 44 M44 56 L39 51 M58 58 L63 53 M52 62 L57 58" stroke="#7A2018" stroke-width="2.5" stroke-linecap="round"/>
      <circle cx="46" cy="42" r="2" fill="#1F2B22"/>
    </svg>`,
    friedFish: `<svg viewBox="0 0 100 100" fill="none" xmlns="http://www.w3.org/2000/svg">
      <ellipse cx="50" cy="78" rx="34" ry="6" fill="#1F2B22" opacity="0.08"/>
      <path d="M20 50 C34 30 62 28 76 42 L68 50 L76 58 C62 72 34 70 20 50 Z" fill="#E8A33D"/>
      <path d="M76 42 L86 36 L82 50 L86 64 L76 58" fill="#D9902A"/>
      <circle cx="34" cy="46" r="3" fill="#1F2B22"/>
      <path d="M40 50 Q50 46 60 50 M42 58 Q50 62 58 58" stroke="#B9761E" stroke-width="2" stroke-linecap="round"/>
    </svg>`,
    beefRendang: `<svg viewBox="0 0 100 100" fill="none" xmlns="http://www.w3.org/2000/svg">
      <ellipse cx="50" cy="80" rx="36" ry="6" fill="#1F2B22" opacity="0.08"/>
      <ellipse cx="50" cy="60" rx="32" ry="16" fill="#5B3418"/>
      <path d="M24 58 C30 46 40 40 50 40 C60 40 70 46 76 58" stroke="#7A4620" stroke-width="3" fill="none" stroke-linecap="round"/>
      <ellipse cx="40" cy="56" rx="9" ry="6" fill="#3F2410"/>
      <ellipse cx="60" cy="52" rx="8" ry="6" fill="#3F2410"/>
      <ellipse cx="52" cy="66" rx="7" ry="5" fill="#3F2410"/>
      <path d="M30 44 Q34 36 40 34 M62 34 Q68 36 72 44" stroke="#E8A33D" stroke-width="2.5" stroke-linecap="round" opacity="0.7"/>
    </svg>`,
    sweetSourTofu: `<svg viewBox="0 0 100 100" fill="none" xmlns="http://www.w3.org/2000/svg">
      <ellipse cx="50" cy="80" rx="34" ry="6" fill="#1F2B22" opacity="0.08"/>
      <rect x="30" y="42" width="16" height="16" rx="2" fill="#F3EEDD" stroke="#D8CFA8" stroke-width="1.5"/>
      <rect x="50" y="48" width="16" height="16" rx="2" fill="#F3EEDD" stroke="#D8CFA8" stroke-width="1.5"/>
      <rect x="40" y="60" width="16" height="16" rx="2" fill="#F3EEDD" stroke="#D8CFA8" stroke-width="1.5"/>
      <circle cx="24" cy="36" r="5" fill="#C0392B"/>
      <circle cx="70" cy="38" r="4" fill="#E8A33D"/>
      <path d="M20 60 Q26 52 34 56" stroke="#C0392B" stroke-width="2" fill="none" stroke-linecap="round" opacity="0.6"/>
    </svg>`,
    chickenSoto: `<svg viewBox="0 0 100 100" fill="none" xmlns="http://www.w3.org/2000/svg">
      <ellipse cx="50" cy="80" rx="34" ry="6" fill="#1F2B22" opacity="0.08"/>
      <path d="M24 52 Q50 42 76 52 L72 68 Q50 76 28 68 Z" fill="#E8A33D" opacity="0.35"/>
      <ellipse cx="50" cy="52" rx="26" ry="9" fill="#F3D9A8"/>
      <path d="M40 50 Q50 46 60 50" stroke="#B9761E" stroke-width="2" stroke-linecap="round" fill="none"/>
      <circle cx="42" cy="52" r="2.5" fill="#C0392B" opacity="0.7"/>
      <circle cx="58" cy="53" r="2.5" fill="#3F6B4F" opacity="0.7"/>
      <path d="M30 40 Q32 32 28 26 M50 38 Q50 30 50 24 M70 40 Q68 32 72 26" stroke="#DCD4BC" stroke-width="2" stroke-linecap="round" fill="none"/>
    </svg>`,
    grilledFishLeaf: `<svg viewBox="0 0 100 100" fill="none" xmlns="http://www.w3.org/2000/svg">
      <ellipse cx="50" cy="80" rx="34" ry="6" fill="#1F2B22" opacity="0.08"/>
      <path d="M22 50 Q50 30 78 50 Q50 70 22 50 Z" fill="#3F6B4F"/>
      <path d="M22 50 Q50 30 78 50" stroke="#2C4C38" stroke-width="2" fill="none"/>
      <ellipse cx="50" cy="50" rx="20" ry="9" fill="#E8A33D"/>
      <path d="M38 48 Q50 44 62 48" stroke="#B9761E" stroke-width="2" stroke-linecap="round" fill="none"/>
      <circle cx="44" cy="50" r="2" fill="#1F2B22"/>
    </svg>`,
    beefSemur: `<svg viewBox="0 0 100 100" fill="none" xmlns="http://www.w3.org/2000/svg">
      <ellipse cx="50" cy="80" rx="34" ry="6" fill="#1F2B22" opacity="0.08"/>
      <ellipse cx="50" cy="58" rx="30" ry="15" fill="#6B3A1E"/>
      <circle cx="38" cy="54" r="7" fill="#E8D5A8"/>
      <circle cx="58" cy="60" r="8" fill="#E8D5A8"/>
      <ellipse cx="48" cy="66" rx="8" ry="6" fill="#4A2814"/>
      <path d="M28 46 Q34 38 42 36 M60 36 Q68 38 74 46" stroke="#8A5A32" stroke-width="2.5" stroke-linecap="round" fill="none"/>
    </svg>`,

    // sides
    stirFrySpinach: `<svg viewBox="0 0 100 100" fill="none" xmlns="http://www.w3.org/2000/svg">
      <ellipse cx="50" cy="80" rx="30" ry="5" fill="#1F2B22" opacity="0.08"/>
      <path d="M30 60 Q26 44 36 32 Q40 44 38 58 Z" fill="#3F6B4F"/>
      <path d="M46 62 Q40 42 52 26 Q58 42 54 60 Z" fill="#4F7D5C"/>
      <path d="M62 60 Q60 44 70 34 Q74 46 68 58 Z" fill="#3F6B4F"/>
      <circle cx="42" cy="66" r="4" fill="#E8A33D"/>
      <circle cx="58" cy="68" r="3.5" fill="#E8A33D"/>
    </svg>`,
    tamarindSoup: `<svg viewBox="0 0 100 100" fill="none" xmlns="http://www.w3.org/2000/svg">
      <ellipse cx="50" cy="80" rx="30" ry="5" fill="#1F2B22" opacity="0.08"/>
      <path d="M24 50 Q50 40 76 50 L72 66 Q50 74 28 66 Z" fill="#C77A2E" opacity="0.5"/>
      <ellipse cx="50" cy="50" rx="24" ry="8" fill="#E8A33D" opacity="0.6"/>
      <circle cx="40" cy="50" r="3" fill="#3F6B4F"/>
      <circle cx="56" cy="52" r="3.5" fill="#E8D5A8"/>
      <circle cx="64" cy="48" r="2.5" fill="#3F6B4F"/>
      <path d="M34 44 Q30 38 32 32" stroke="#B9761E" stroke-width="2" stroke-linecap="round" fill="none"/>
    </svg>`,
    stirFryBeans: `<svg viewBox="0 0 100 100" fill="none" xmlns="http://www.w3.org/2000/svg">
      <ellipse cx="50" cy="80" rx="30" ry="5" fill="#1F2B22" opacity="0.08"/>
      <path d="M28 58 Q26 46 34 40 Q40 46 40 58 Q40 64 34 66 Q28 64 28 58 Z" fill="#3F6B4F"/>
      <path d="M44 60 Q42 48 50 42 Q56 48 56 60 Q56 66 50 68 Q44 66 44 60 Z" fill="#4F7D5C"/>
      <path d="M60 58 Q58 46 66 40 Q72 46 72 58 Q72 64 66 66 Q60 64 60 58 Z" fill="#3F6B4F"/>
      <circle cx="38" cy="70" r="2.5" fill="#C0392B"/>
    </svg>`,
    cassavaLeaves: `<svg viewBox="0 0 100 100" fill="none" xmlns="http://www.w3.org/2000/svg">
      <ellipse cx="50" cy="80" rx="30" ry="5" fill="#1F2B22" opacity="0.08"/>
      <ellipse cx="50" cy="58" rx="26" ry="14" fill="#4F7D5C"/>
      <path d="M32 54 Q50 48 68 54" stroke="#2C4C38" stroke-width="2" fill="none" stroke-linecap="round"/>
      <path d="M36 62 Q50 58 64 62" stroke="#2C4C38" stroke-width="2" fill="none" stroke-linecap="round"/>
      <circle cx="42" cy="50" r="2" fill="#E8D5A8"/>
      <circle cx="58" cy="66" r="2" fill="#E8D5A8"/>
    </svg>`,
    beanSproutSalad: `<svg viewBox="0 0 100 100" fill="none" xmlns="http://www.w3.org/2000/svg">
      <ellipse cx="50" cy="80" rx="30" ry="5" fill="#1F2B22" opacity="0.08"/>
      <path d="M30 66 Q28 52 34 42" stroke="#E8D5A8" stroke-width="3" stroke-linecap="round" fill="none"/>
      <path d="M42 68 Q40 50 48 38" stroke="#E8D5A8" stroke-width="3" stroke-linecap="round" fill="none"/>
      <path d="M56 68 Q58 50 52 38" stroke="#E8D5A8" stroke-width="3" stroke-linecap="round" fill="none"/>
      <path d="M70 66 Q72 52 66 42" stroke="#E8D5A8" stroke-width="3" stroke-linecap="round" fill="none"/>
      <ellipse cx="34" cy="40" rx="3" ry="4" fill="#F3EEDD"/>
      <ellipse cx="48" cy="36" rx="3" ry="4" fill="#F3EEDD"/>
      <ellipse cx="52" cy="36" rx="3" ry="4" fill="#F3EEDD"/>
      <ellipse cx="66" cy="40" rx="3" ry="4" fill="#F3EEDD"/>
      <path d="M28 66 Q50 74 72 66" stroke="#4F7D5C" stroke-width="2.5" fill="none" stroke-linecap="round"/>
    </svg>`,
    sauteedSpinach: `<svg viewBox="0 0 100 100" fill="none" xmlns="http://www.w3.org/2000/svg">
      <ellipse cx="50" cy="80" rx="30" ry="5" fill="#1F2B22" opacity="0.08"/>
      <path d="M26 62 Q40 66 50 60 Q60 66 74 62" stroke="#3F6B4F" stroke-width="4" fill="none" stroke-linecap="round"/>
      <path d="M32 54 Q42 58 50 52 Q58 58 68 54" stroke="#4F7D5C" stroke-width="4" fill="none" stroke-linecap="round"/>
      <circle cx="40" cy="46" r="3" fill="#C0392B"/>
      <circle cx="60" cy="44" r="2.5" fill="#E8A33D"/>
    </svg>`,
    steamedChayote: `<svg viewBox="0 0 100 100" fill="none" xmlns="http://www.w3.org/2000/svg">
      <ellipse cx="50" cy="80" rx="30" ry="5" fill="#1F2B22" opacity="0.08"/>
      <path d="M34 42 Q26 50 30 62 Q36 72 50 72 Q64 72 70 62 Q74 50 66 42 Q58 34 50 40 Q42 34 34 42 Z" fill="#8FBF9E"/>
      <path d="M50 40 L50 72" stroke="#5E9270" stroke-width="1.5" opacity="0.6"/>
      <path d="M38 50 Q50 46 62 50" stroke="#5E9270" stroke-width="1.5" fill="none" opacity="0.6"/>
    </svg>`,

    rice: `<svg viewBox="0 0 100 100" fill="none" xmlns="http://www.w3.org/2000/svg">
      <ellipse cx="50" cy="60" rx="28" ry="16" fill="#FDFBF4"/>
      <ellipse cx="50" cy="55" rx="26" ry="14" fill="#FFFFFF"/>
      <path d="M34 52 Q50 44 66 52" stroke="#EFE9D8" stroke-width="2" fill="none" stroke-linecap="round"/>
      <path d="M38 58 Q50 52 62 58" stroke="#EFE9D8" stroke-width="2" fill="none" stroke-linecap="round"/>
    </svg>`,
  };

export const mainArtKey = {
    'Sweet Soy-Glazed Grilled Chicken':'grilledChicken',
    'Fried Tilapia':'friedFish',
    'Beef Rendang':'beefRendang',
    'Sweet & Sour Tofu':'sweetSourTofu',
    'Chicken Soto Soup':'chickenSoto',
    'Grilled Fish in Banana Leaf':'grilledFishLeaf',
    'Beef & Potato Semur':'beefSemur',
  };
export const sideArtKey = {
    'Stir-Fried Spinach & Corn (Sayur Bening Bayam Jagung)':'stirFrySpinach',
    'Tamarind Vegetable Soup (Sayur Asem)':'tamarindSoup',
    'Stir-Fried Green Beans':'stirFryBeans',
    'Steamed Cassava Leaves':'cassavaLeaves',
    'Bean Sprout & Cabbage Salad':'beanSproutSalad',
    'Sautéed Water Spinach':'sauteedSpinach',
    'Steamed Chayote':'steamedChayote',
  };
