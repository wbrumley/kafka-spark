import json
from src.generator.event_generator import SecurityEventGenerator

def main():
    """Test the security event generator without Kafka integration"""
    print("Testing Security Event Generator")
    
    # Create generator
    generator = SecurityEventGenerator()
    
    # Generate 5 sample events
    print("\nGenerating 5 sample events:\n")
    
    for i in range(5):
        event = generator.generate_event()
        event_dict = event.model_dump()
        event_dict["timestamp"] = event_dict["timestamp"].isoformat() + "Z"
        event_dict["event_type"] = str(event_dict["event_type"])
        
        print(f"Event {i+1}:")
        print(json.dumps(event_dict, indent=2))
        print("-" * 80)

if __name__ == "__main__":
    main() 