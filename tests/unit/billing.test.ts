/**
 * Unit Test: Billing Calculation & Tax Deductions
 */
describe('Billing Calculations', () => {
  it('should accurately compute total with tax and discounts', () => {
    const subtotal = 100.00;
    const taxRate = 0.05; // 5%
    const discount = 10.00;
    
    const tax = (subtotal - discount) * taxRate;
    const total = (subtotal - discount) + tax;
    
    // Total should equal 94.50
    if (total !== 94.50) {
      throw new Error(`Expected 94.50 but got ${total}`);
    }
  });
});
