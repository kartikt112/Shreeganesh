import json
from ai.balloon_generator import place_balloons, generate_ballooned_image
with open('/tmp/swivel_tube_features.json', 'r') as f:
    features = json.load(f)['features']
    
# Transform the 14-stage structure back to the structure expected by balloon_generator
for f in features:
    f['box_2d'] = f.get('bbox')
    f['anchor_point'] = f.get('anchor')
    # clear out old placement
    f.pop('balloon_position', None)
    f.pop('leader_start', None)
    f.pop('leader_bend', None)
    f.pop('leader_end', None)

place_balloons('/tmp/swivel_tube_drawing.png', features)
generate_ballooned_image('/tmp/swivel_tube_drawing.png', features, '/tmp/swivel_tube_margin_test.png')
