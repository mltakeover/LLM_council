export function scrollElementToBottom(element, behavior = 'smooth') {
  if (!element || typeof element.scrollTo !== 'function') {
    return false;
  }

  element.scrollTo({
    top: element.scrollHeight,
    behavior,
  });
  return true;
}
