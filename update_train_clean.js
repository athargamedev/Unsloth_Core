const fs = require('fs');
const path = require('path');
const crypto = require('crypto');

function computeContentHash(messages) {
  const contentString = messages.map(m => m.content || "").join("");
  return crypto.createHash('sha256').update(contentString).digest('hex');
}

function updateDataset() {
  const filePath = '/home/athar/Projects/Unsloth_Core/data/datasets/chef_assistant/ollama/train_clean.jsonl';
  
  if (!fs.existsSync(filePath)) {
    throw new Error(`File not found: ${filePath}`);
  }

  const rawContent = fs.readFileSync(filePath, 'utf8');
  const lines = rawContent.split('\n').filter(Boolean);

  if (lines.length < 3) {
    throw new Error(`Expected at least 3 lines, but found only ${lines.length}`);
  }

  const thirdLine = lines[2];
  let data;
  try {
    data = JSON.parse(thirdLine);
  } catch (err) {
    throw new Error(`Failed to parse third line as JSON: ${err.message}`);
  }

  const messages = data.messages;
  if (!messages || !Array.isArray(messages)) {
    throw new Error('Third line JSON is missing expected "messages" array');
  }

  const assistantMessage = messages.find(m => m.role === 'assistant');
  if (!assistantMessage) {
    throw new Error('No assistant message found in messages array of the third line');
  }

  // Ensure user prompt matches expected to prevent wrong line modification
  const userMessage = messages.find(m => m.role === 'user');
  if (!userMessage || userMessage.content !== "What should I call you?") {
    throw new Error(`Expected user prompt to be "What should I call you?", but got: ${userMessage ? userMessage.content : 'none'}`);
  }

  // Update assistant response content
  assistantMessage.content = "I am ChefAssistant. I guide your cooking steps and food safety.";

  // Recompute content_hash
  const newHash = computeContentHash(messages);
  if (!data.metadata) {
    data.metadata = {};
  }
  data.metadata.content_hash = newHash;

  // Serialize line back to JSON
  lines[2] = JSON.stringify(data);

  // Write file back
  fs.writeFileSync(filePath, lines.join('\n') + '\n', 'utf8');
  console.log(`Successfully updated row 3. New content_hash: ${newHash}`);
}

try {
  updateDataset();
} catch (error) {
  console.error("FATAL ERROR during dataset update:", error.message);
  process.exit(1);
}
